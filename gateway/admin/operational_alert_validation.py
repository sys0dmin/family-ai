"""Isolated validation of operational alert lifecycle and thresholds."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from gateway.admin.monitoring_schemas import (
    DatabaseStatus,
    InfrastructureStatusResponse,
    NodeStatus,
    ResourceUsage,
)
from gateway.admin.operational_alert_schemas import (
    OperationalAlertSelfTestResponse,
    OperationalAlertSelfTestScenario,
)
from gateway.admin.operational_alert_service import OperationalAlertService
from gateway.admin.voice_observability_schemas import (
    MetricsSource,
    VoiceObservabilityResponse,
)
from gateway.app.config import Settings
from gateway.app.models.operational_alert import OperationalAlert


class OperationalAlertValidator:
    """Exercise alert state transitions without touching runtime data or metrics."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def run(self) -> OperationalAlertSelfTestResponse:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        OperationalAlert.__table__.create(engine)
        scenarios: list[OperationalAlertSelfTestScenario] = []
        try:
            with Session(engine) as session:
                self._run_lifecycle(session, scenarios)
        except Exception as exc:  # pragma: no cover - defensive API boundary
            scenarios.append(
                OperationalAlertSelfTestScenario(
                    name="self_test_runtime",
                    status="failed",
                    detail=f"Изолированная проверка завершилась ошибкой {type(exc).__name__}.",
                )
            )
        finally:
            engine.dispose()
        return OperationalAlertSelfTestResponse(
            status=(
                "passed"
                if scenarios and all(item.status == "passed" for item in scenarios)
                else "failed"
            ),
            checked_at=datetime.now(UTC),
            scenarios=scenarios,
        )

    def _run_lifecycle(
        self,
        session: Session,
        scenarios: list[OperationalAlertSelfTestScenario],
    ) -> None:
        service = OperationalAlertService(session, self._settings)
        healthy = service.reconcile(self._infrastructure(), self._voice())
        self._record(
            scenarios,
            "healthy_baseline",
            not healthy.active and not healthy.history,
            "Чистый снимок не создаёт событий.",
        )

        warning = service.reconcile(
            self._infrastructure(disk_used_percent=86),
            self._voice(queue_depth=2, error_count=3),
        )
        warning_ids = {item.metric: item.id for item in warning.active}
        self._record(
            scenarios,
            "warning_thresholds",
            set(warning_ids) == {"disk_free_percent", "queue_depth", "voice_error_streak"}
            and all(item.severity == "warning" for item in warning.active),
            "Диск, очередь и серия ошибок открывают warning-эпизоды.",
        )

        critical = service.reconcile(
            self._infrastructure(disk_used_percent=93),
            self._voice(queue_depth=4, error_count=5),
        )
        critical_ids = {item.metric: item.id for item in critical.active}
        self._record(
            scenarios,
            "critical_escalation",
            critical_ids == warning_ids
            and all(item.severity == "critical" for item in critical.active),
            "Те же эпизоды повышаются до critical без дублирования.",
        )

        acknowledged = [
            service.acknowledge(item.id, "isolated-self-test") for item in critical.active
        ]
        self._record(
            scenarios,
            "acknowledgement",
            all(item is not None and item.acknowledged_at is not None for item in acknowledged),
            "Подтверждение фиксируется и не закрывает активную проблему.",
        )

        recovered = service.reconcile(self._infrastructure(), self._voice())
        self._record(
            scenarios,
            "recovery_history",
            not recovered.active
            and len(recovered.history) == 3
            and all(item.resolved_at is not None for item in recovered.history),
            "Нормализация метрик закрывает эпизоды и сохраняет техническую историю.",
        )

        repeated = service.reconcile(
            self._infrastructure(disk_used_percent=86),
            self._voice(),
        )
        repeated_disk = next(
            (item for item in repeated.active if item.metric == "disk_free_percent"), None
        )
        self._record(
            scenarios,
            "repeat_episode",
            repeated_disk is not None
            and repeated_disk.id != warning_ids["disk_free_percent"]
            and repeated_disk.occurrence_count == 1,
            "Повторная деградация создаёт новый эпизод.",
        )

        service.reconcile(self._infrastructure(), self._voice())
        unavailable = service.reconcile(
            self._infrastructure(node_down=True, database_down=True),
            self._voice(gateway_down=True, speech_down=True),
        )
        self._record(
            scenarios,
            "availability_failures",
            len(unavailable.active) == 4
            and {item.metric for item in unavailable.active}
            == {
                "availability",
                "postgresql_availability",
                "voice_metrics_availability",
            }
            and sum(item.severity == "critical" for item in unavailable.active) == 3,
            "Недоступность локальных компонентов создаёт allowlisted события.",
        )

    @staticmethod
    def _record(
        scenarios: list[OperationalAlertSelfTestScenario],
        name: str,
        passed: bool,
        detail: str,
    ) -> None:
        scenarios.append(
            OperationalAlertSelfTestScenario(
                name=name,
                status="passed" if passed else "failed",
                detail=detail,
            )
        )

    @staticmethod
    def _infrastructure(
        *,
        disk_used_percent: float | None = None,
        node_down: bool = False,
        database_down: bool = False,
    ) -> InfrastructureStatusResponse:
        disk = None
        if disk_used_percent is not None:
            disk = ResourceUsage(
                used_bytes=round(disk_used_percent * 10),
                total_bytes=1000,
                percent=disk_used_percent,
            )
        return InfrastructureStatusResponse(
            status="down" if node_down or database_down else "healthy",
            checked_at=datetime.now(UTC),
            nodes=[
                NodeStatus(
                    id="speech",
                    name="family-ai-speech",
                    role="Local STT · TTS",
                    status="down" if node_down else "healthy",
                    disk=disk,
                )
            ],
            database=DatabaseStatus(status="down" if database_down else "healthy"),
        )

    @staticmethod
    def _voice(
        *,
        queue_depth: int = 0,
        error_count: int = 0,
        gateway_down: bool = False,
        speech_down: bool = False,
    ) -> VoiceObservabilityResponse:
        recent = [{"status": "error", "error_stage": "synthetic"}] * error_count
        return VoiceObservabilityResponse(
            gateway=MetricsSource(
                status="down" if gateway_down else "healthy",
                data=None if gateway_down else {"recent": recent},
            ),
            speech=MetricsSource(
                status="down" if speech_down else "healthy",
                data=None if speech_down else {"queue_depth": queue_depth},
            ),
        )
