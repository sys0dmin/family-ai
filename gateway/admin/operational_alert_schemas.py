"""Contracts for local operational warnings and their technical history."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from gateway.admin.monitoring_schemas import InfrastructureStatusResponse
from gateway.admin.voice_observability_schemas import VoiceObservabilityResponse

AlertSeverity = Literal["warning", "critical"]


class OperationalAlertResponse(BaseModel):
    id: UUID
    scope: str
    metric: str
    severity: AlertSeverity
    title: str
    detail: str
    current_value: float | None
    threshold_value: float | None
    occurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    resolved_at: datetime | None


class OperationalThresholdsResponse(BaseModel):
    disk_warning_free_percent: float
    disk_critical_free_percent: float
    speech_queue_warning: int
    speech_queue_critical: int
    voice_error_streak_warning: int
    voice_error_streak_critical: int
    history_days: int


class OperationalAlertCollection(BaseModel):
    active: list[OperationalAlertResponse]
    history: list[OperationalAlertResponse]
    thresholds: OperationalThresholdsResponse


class OperationalOverviewResponse(BaseModel):
    infrastructure: InfrastructureStatusResponse
    voice: VoiceObservabilityResponse
    alerts: OperationalAlertCollection
