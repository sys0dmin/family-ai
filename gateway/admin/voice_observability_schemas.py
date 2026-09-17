"""Contracts for voice pipeline observability in the Admin UI."""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class MetricsSource(BaseModel):
    status: str
    data: dict[str, Any] | None = None
    message: str | None = None


class VoiceDailyMetricResponse(BaseModel):
    """One content-free operation aggregate for one UTC calendar day."""

    metric_date: date
    mode: str
    total_count: int
    success_count: int
    error_count: int
    cancellation_count: int
    recording_average_ms: int | None = None
    stt_average_ms: int | None = None
    vision_average_ms: int | None = None
    llm_average_ms: int | None = None
    tts_average_ms: int | None = None
    first_audio_average_ms: int | None = None
    playback_average_ms: int | None = None
    total_duration_average_ms: int | None = None


class VoiceObservabilityResponse(BaseModel):
    gateway: MetricsSource
    speech: MetricsSource
    history: list[VoiceDailyMetricResponse] = Field(default_factory=list)
