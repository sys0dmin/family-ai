"""Schemas for the protected AI test studio."""

from pydantic import BaseModel, Field


class AgentTestRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=4000)


class AgentTestResponse(BaseModel):
    raw_response: str
    final_response: str
    safety_status: str
    safety_rule_id: str | None = None
    safety_reason: str | None = None
    llm_duration_ms: int | None = None


class SpeechPreviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    voice: str = Field(min_length=1, max_length=100)


class TranscriptionTestResponse(BaseModel):
    text: str
    confidence: float | None = None
    duration_ms: int | None = None


class VisionTestResponse(BaseModel):
    description: str
