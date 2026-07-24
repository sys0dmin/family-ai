"""Contracts for validated Speech runtime settings."""

from pydantic import BaseModel, Field


class SpeechRuntimeSettingsUpdate(BaseModel):
    stt_beam_size: int = Field(ge=1, le=10)
    stt_vad_filter: bool


class SpeechRuntimeSettings(BaseModel):
    stt_beam_size: int
    stt_vad_filter: bool
    restart_scheduled: bool = False
    instance_id: str
