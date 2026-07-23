"""Contracts for voice pipeline observability in the Admin UI."""

from typing import Any

from pydantic import BaseModel


class MetricsSource(BaseModel):
    status: str
    data: dict[str, Any] | None = None
    message: str | None = None


class VoiceObservabilityResponse(BaseModel):
    gateway: MetricsSource
    speech: MetricsSource
