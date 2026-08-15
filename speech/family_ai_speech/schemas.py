"""OpenAI-compatible and internal runtime schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SynthesisRequest(BaseModel):
    """Subset of the OpenAI speech request used by the Gateway."""

    model: str = Field(min_length=1, max_length=200)
    input: str = Field(min_length=1)
    voice: str = Field(min_length=1, max_length=100)
    response_format: Literal["wav"] = "wav"


class TranscriptionSegmentResponse(BaseModel):
    """OpenAI-compatible verbose transcription segment."""

    id: int
    seek: int = 0
    start: float
    end: float
    text: str
    tokens: list[int] = Field(default_factory=list)
    temperature: float = 0.0
    avg_logprob: float
    compression_ratio: float = 0.0
    no_speech_prob: float


class TranscriptionVerboseResponse(BaseModel):
    """Verbose STT response understood by the OpenAI client."""

    task: Literal["transcribe"] = "transcribe"
    language: str
    duration: float
    text: str
    segments: list[TranscriptionSegmentResponse]


class StageRuntimeMetrics(BaseModel):
    """Bounded aggregate for one serialized inference stage."""

    calls: int
    errors: int
    average_processing_ms: float | None
    last_processing_ms: float | None
    average_queue_wait_ms: float | None
    last_queue_wait_ms: float | None


class RuntimeIdentityResponse(BaseModel):
    """Content-free immutable release identity."""

    component: Literal["speech"]
    app_version: str
    actual_commit: str | None
    expected_commit: str | None
    matches_expected: bool | None


class SpeechRuntimeMetricsResponse(BaseModel):
    """Current queue and inference statistics without audio or text."""

    generated_at: datetime
    uptime_seconds: float
    queue_depth: int
    active_stage: Literal["stt", "tts"] | None
    stt: StageRuntimeMetrics
    tts: StageRuntimeMetrics
    runtime: RuntimeIdentityResponse | None = None


class CalibrationPrompt(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_-]{1,50}$")
    expected_text: str = Field(max_length=500)
    kind: Literal["speech", "silence"]


class CalibrationStartRequest(BaseModel):
    prompts: list[CalibrationPrompt] = Field(min_length=1, max_length=30)
    initial_prompt: str = Field(min_length=1, max_length=1000)


class CalibrationConfigurationResult(BaseModel):
    beam_size: int
    vad_filter: bool
    spoken_accuracy_percent: float
    silence_rejection_percent: float
    average_processing_ms: float
    p95_processing_ms: float
    average_confidence: float | None


class CalibrationStateResponse(BaseModel):
    id: str
    status: Literal["collecting", "running", "completed", "failed", "cancelled"]
    created_at: datetime
    expires_at: datetime
    prompts_total: int
    samples_collected: int
    collected_prompt_ids: list[str]
    current_trial: int = 0
    total_trials: int = 0
    results: list[CalibrationConfigurationResult] = Field(default_factory=list)
    recommended_beam_size: int | None = None
    recommended_vad_filter: bool | None = None
    error: str | None = None


class RuntimeSettingsUpdateRequest(BaseModel):
    stt_beam_size: int = Field(ge=1, le=10)
    stt_vad_filter: bool


class RuntimeSettingsResponse(BaseModel):
    stt_beam_size: int
    stt_vad_filter: bool
    restart_scheduled: bool = False
    instance_id: str
