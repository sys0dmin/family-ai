"""Privacy-safe daily aggregates for completed voice operations."""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from gateway.app.db.base import Base


class VoiceDailyMetric(Base):
    """One UTC day and operation mode, without content or identifiers."""

    __tablename__ = "voice_daily_metrics"

    metric_date: Mapped[date] = mapped_column(Date, primary_key=True)
    mode: Mapped[str] = mapped_column(String(32), primary_key=True)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancellation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recording_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recording_total_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    stt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stt_total_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    vision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vision_total_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    llm_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_total_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tts_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tts_total_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    first_audio_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_audio_total_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    playback_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    playback_total_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_duration_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_duration_total_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
