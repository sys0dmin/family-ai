"""Gateway contracts for child-speech calibration."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CalibrationPromptView(BaseModel):
    id: str
    kind: Literal["speech", "silence"]
    phrase: str
    icon: str


class CalibrationDiscoveryResponse(BaseModel):
    active: bool
    session_id: str | None = None
    prompts: list[CalibrationPromptView] = Field(default_factory=list)
    collected_prompt_ids: list[str] = Field(default_factory=list)


class CalibrationConfigurationResult(BaseModel):
    beam_size: int
    vad_filter: bool
    spoken_accuracy_percent: float
    silence_rejection_percent: float
    average_processing_ms: float
    p95_processing_ms: float
    average_confidence: float | None


class CalibrationStatusResponse(BaseModel):
    id: str
    status: Literal["collecting", "running", "completed", "failed", "cancelled"]
    created_at: datetime
    expires_at: datetime
    prompts_total: int
    samples_collected: int
    collected_prompt_ids: list[str]
    current_trial: int
    total_trials: int
    results: list[CalibrationConfigurationResult]
    recommended_beam_size: int | None
    recommended_vad_filter: bool | None
    error: str | None
