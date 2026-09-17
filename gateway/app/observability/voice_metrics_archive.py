"""Durable, content-free voice metrics kept independently of process uptime."""

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from gateway.app.db.session import get_session_factory
from gateway.app.models.voice_daily_metric import VoiceDailyMetric
from gateway.app.observability.voice_metrics import VoiceTurnSample

logger = logging.getLogger(__name__)

_STAGES = (
    ("recording", "recording_duration_ms"),
    ("stt", "stt_duration_ms"),
    ("vision", "vision_duration_ms"),
    ("llm", "llm_duration_ms"),
    ("tts", "tts_duration_ms"),
    ("first_audio", "first_audio_ready_ms"),
    ("playback", "client_first_playback_ms"),
    ("total_duration", "total_duration_ms"),
)


class VoiceMetricsArchive:
    """Persist only daily counters and duration sums; never raw turns."""

    def __init__(
        self,
        session_factory: Callable = get_session_factory,
        retention_days: int = 30,
    ) -> None:
        self._session_factory = session_factory
        self._retention_days = max(1, retention_days)

    def record(self, sample: VoiceTurnSample) -> None:
        try:
            self._upsert(sample)
        except Exception:
            # Observability must not make a child-facing turn fail.
            logger.exception("voice_metrics_archive_write_failed")

    def record_playback(self, sample: VoiceTurnSample) -> None:
        """Add a client playback report without counting the turn twice."""

        if sample.client_first_playback_ms is None:
            return
        values: dict[str, int | str | date] = {
            "metric_date": datetime.now(UTC).date(),
            "mode": sample.mode,
            "playback_count": 1,
            "playback_total_ms": sample.client_first_playback_ms,
        }
        try:
            self._upsert_values(values)
        except Exception:
            logger.exception("voice_metrics_archive_playback_write_failed")

    def history(self, days: int = 30) -> list[VoiceDailyMetric]:
        cutoff = datetime.now(UTC).date() - timedelta(days=max(1, days) - 1)
        session = self._session_factory()()
        try:
            return list(
                session.scalars(
                    select(VoiceDailyMetric)
                    .where(VoiceDailyMetric.metric_date >= cutoff)
                    .order_by(VoiceDailyMetric.metric_date.asc(), VoiceDailyMetric.mode.asc())
                )
            )
        except Exception:
            logger.exception("voice_metrics_archive_read_failed")
            return []
        finally:
            session.close()

    def _upsert(self, sample: VoiceTurnSample) -> None:
        metric_date = datetime.now(UTC).date()
        values: dict[str, int | str | date] = {
            "metric_date": metric_date,
            "mode": sample.mode,
            "total_count": 1,
            "success_count": int(sample.status == "success"),
            "error_count": int(sample.status == "error"),
            "cancellation_count": int(sample.cancelled),
        }
        for prefix, attribute in _STAGES:
            duration = getattr(sample, attribute)
            values[f"{prefix}_count"] = int(duration is not None)
            values[f"{prefix}_total_ms"] = duration or 0

        self._upsert_values(values)

    def _upsert_values(self, values: dict[str, int | str | date]) -> None:
        session = self._session_factory()()
        try:
            self._increment(session, values)
            session.commit()
        except IntegrityError:
            # Two voice slots may finish their first turn of a day together.
            session.rollback()
            self._increment(session, values)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _increment(self, session, values: dict[str, int | str | date]) -> None:
        metric = session.get(
            VoiceDailyMetric,
            (values["metric_date"], values["mode"]),
        )
        if metric is None:
            metric = VoiceDailyMetric(
                metric_date=values["metric_date"],
                mode=values["mode"],
            )
            session.add(metric)
        for field, value in values.items():
            if field not in {"metric_date", "mode"}:
                setattr(metric, field, (getattr(metric, field) or 0) + value)

        cutoff = datetime.now(UTC).date() - timedelta(days=self._retention_days - 1)
        session.execute(delete(VoiceDailyMetric).where(VoiceDailyMetric.metric_date < cutoff))
