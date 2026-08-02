"""Evaluate and persist local operational degradation episodes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from gateway.admin.monitoring_schemas import InfrastructureStatusResponse
from gateway.admin.operational_alert_schemas import (
    OperationalAlertCollection,
    OperationalAlertResponse,
    OperationalThresholdsResponse,
)
from gateway.admin.voice_observability_schemas import VoiceObservabilityResponse
from gateway.app.config import Settings
from gateway.app.models.operational_alert import OperationalAlert


@dataclass(frozen=True)
class AlertCandidate:
    fingerprint: str
    scope: str
    metric: str
    severity: str
    title: str
    detail: str
    current_value: float | None = None
    threshold_value: float | None = None


class OperationalAlertService:
    """Turn allowlisted technical metrics into acknowledged alert episodes."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def reconcile(
        self,
        infrastructure: InfrastructureStatusResponse,
        voice: VoiceObservabilityResponse,
    ) -> OperationalAlertCollection:
        now = datetime.now(UTC)
        candidates = {
            candidate.fingerprint: candidate for candidate in self._evaluate(infrastructure, voice)
        }
        active_rows = self._session.scalars(
            select(OperationalAlert).where(OperationalAlert.resolved_at.is_(None))
        ).all()
        rows_by_fingerprint = {row.fingerprint: row for row in active_rows}

        for fingerprint, candidate in candidates.items():
            row = rows_by_fingerprint.get(fingerprint)
            if row is None:
                self._session.add(
                    OperationalAlert(
                        id=uuid.uuid4(),
                        fingerprint=fingerprint,
                        scope=candidate.scope,
                        metric=candidate.metric,
                        severity=candidate.severity,
                        title=candidate.title,
                        detail=candidate.detail,
                        current_value=candidate.current_value,
                        threshold_value=candidate.threshold_value,
                        occurrence_count=1,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
                continue
            row.severity = candidate.severity
            row.title = candidate.title
            row.detail = candidate.detail
            row.current_value = candidate.current_value
            row.threshold_value = candidate.threshold_value
            row.last_seen_at = now
            row.occurrence_count += 1

        for row in active_rows:
            if row.fingerprint not in candidates:
                row.resolved_at = now
                row.last_seen_at = now

        cutoff = now - timedelta(days=self._settings.operational_alert_history_days)
        self._session.execute(
            delete(OperationalAlert).where(
                OperationalAlert.resolved_at.is_not(None),
                OperationalAlert.resolved_at < cutoff,
            )
        )
        self._session.flush()
        return self.list_alerts()

    def list_alerts(self, history_limit: int = 30) -> OperationalAlertCollection:
        active = self._session.scalars(
            select(OperationalAlert)
            .where(OperationalAlert.resolved_at.is_(None))
            .order_by(OperationalAlert.severity, OperationalAlert.first_seen_at)
        ).all()
        history = self._session.scalars(
            select(OperationalAlert)
            .where(OperationalAlert.resolved_at.is_not(None))
            .order_by(OperationalAlert.resolved_at.desc())
            .limit(history_limit)
        ).all()
        return OperationalAlertCollection(
            active=[self._response(row) for row in active],
            history=[self._response(row) for row in history],
            thresholds=self._thresholds(),
        )

    def acknowledge(self, alert_id: uuid.UUID, username: str) -> OperationalAlertResponse | None:
        row = self._session.get(OperationalAlert, alert_id)
        if row is None or row.resolved_at is not None:
            return None
        if row.acknowledged_at is None:
            row.acknowledged_at = datetime.now(UTC)
            row.acknowledged_by = username[:120]
            self._session.flush()
        return self._response(row)

    def _evaluate(
        self,
        infrastructure: InfrastructureStatusResponse,
        voice: VoiceObservabilityResponse,
    ) -> list[AlertCandidate]:
        candidates: list[AlertCandidate] = []
        for node in infrastructure.nodes:
            if node.status == "down":
                candidates.append(
                    AlertCandidate(
                        fingerprint=f"node:{node.id}:availability",
                        scope=node.id,
                        metric="availability",
                        severity="critical",
                        title=f"{node.name} недоступен",
                        detail="Node exporter не вернул локальный технический снимок.",
                    )
                )
            if node.disk is not None:
                free_percent = round(100 - node.disk.percent, 1)
                candidate = self._threshold_candidate(
                    fingerprint=f"node:{node.id}:disk_free_percent",
                    scope=node.id,
                    metric="disk_free_percent",
                    title=f"Мало места на {node.name}",
                    value=free_percent,
                    warning=self._settings.operational_disk_warning_free_percent,
                    critical=self._settings.operational_disk_critical_free_percent,
                    lower_is_worse=True,
                    unit="% свободно",
                )
                if candidate:
                    candidates.append(candidate)

        if infrastructure.database.status == "down":
            candidates.append(
                AlertCandidate(
                    fingerprint="database:postgresql:availability",
                    scope="database",
                    metric="postgresql_availability",
                    severity="critical",
                    title="PostgreSQL недоступен",
                    detail="Локальная проверка базы данных завершилась ошибкой.",
                )
            )

        for source_name, source in (("gateway", voice.gateway), ("speech", voice.speech)):
            if source.status == "down":
                candidates.append(
                    AlertCandidate(
                        fingerprint=f"voice:{source_name}:metrics_availability",
                        scope=source_name,
                        metric="voice_metrics_availability",
                        severity="critical" if source_name == "speech" else "warning",
                        title=f"Voice-метрики {source_name} недоступны",
                        detail="Внутренний endpoint технических метрик не отвечает.",
                    )
                )

        speech_data = voice.speech.data or {}
        queue_depth = self._number(speech_data.get("queue_depth"))
        if queue_depth is not None:
            queue_candidate = self._threshold_candidate(
                fingerprint="voice:speech:queue_depth",
                scope="speech",
                metric="queue_depth",
                title="Очередь Speech растёт",
                value=queue_depth,
                warning=float(self._settings.operational_speech_queue_warning),
                critical=float(self._settings.operational_speech_queue_critical),
                lower_is_worse=False,
                unit="запросов",
            )
            if queue_candidate:
                candidates.append(queue_candidate)

        error_streak = self._voice_error_streak((voice.gateway.data or {}).get("recent"))
        streak_candidate = self._threshold_candidate(
            fingerprint="voice:gateway:error_streak",
            scope="gateway",
            metric="voice_error_streak",
            title="Серия ошибок голосового конвейера",
            value=float(error_streak),
            warning=float(self._settings.operational_voice_error_streak_warning),
            critical=float(self._settings.operational_voice_error_streak_critical),
            lower_is_worse=False,
            unit="ошибок подряд",
        )
        if streak_candidate:
            candidates.append(streak_candidate)
        return candidates

    def _threshold_candidate(
        self,
        *,
        fingerprint: str,
        scope: str,
        metric: str,
        title: str,
        value: float,
        warning: float,
        critical: float,
        lower_is_worse: bool,
        unit: str,
    ) -> AlertCandidate | None:
        critical_hit = value <= critical if lower_is_worse else value >= critical
        warning_hit = value <= warning if lower_is_worse else value >= warning
        if not warning_hit:
            return None
        severity = "critical" if critical_hit else "warning"
        threshold = critical if critical_hit else warning
        return AlertCandidate(
            fingerprint=fingerprint,
            scope=scope,
            metric=metric,
            severity=severity,
            title=title,
            detail=f"Текущее значение: {value:g} {unit}; порог: {threshold:g}.",
            current_value=value,
            threshold_value=threshold,
        )

    @staticmethod
    def _voice_error_streak(recent: object) -> int:
        if not isinstance(recent, list):
            return 0
        streak = 0
        for sample in reversed(recent):
            if not isinstance(sample, dict) or sample.get("status") != "error":
                break
            if sample.get("cancelled") is True:
                break
            streak += 1
        return streak

    @staticmethod
    def _number(value: object) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)

    def _thresholds(self) -> OperationalThresholdsResponse:
        return OperationalThresholdsResponse(
            disk_warning_free_percent=self._settings.operational_disk_warning_free_percent,
            disk_critical_free_percent=self._settings.operational_disk_critical_free_percent,
            speech_queue_warning=self._settings.operational_speech_queue_warning,
            speech_queue_critical=self._settings.operational_speech_queue_critical,
            voice_error_streak_warning=self._settings.operational_voice_error_streak_warning,
            voice_error_streak_critical=self._settings.operational_voice_error_streak_critical,
            history_days=self._settings.operational_alert_history_days,
        )

    @staticmethod
    def _response(row: OperationalAlert) -> OperationalAlertResponse:
        return OperationalAlertResponse.model_validate(row, from_attributes=True)
