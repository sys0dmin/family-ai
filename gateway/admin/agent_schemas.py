"""Validated contracts for protected agent administration."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    system_prompt: str
    created_by: str
    created_at: datetime
    is_active: bool


class AdminAgentResponse(BaseModel):
    id: str
    display_name: str
    description: str
    icon: str
    color: str
    greeting: str
    tts_voice: str | None
    tools: list[str]
    permissions: list[str]
    enabled: bool
    sort_order: int
    active_revision_id: uuid.UUID | None
    revisions: list[AgentRevisionResponse]


class AdminAgentListResponse(BaseModel):
    safety_baseline: str
    safety_baseline_version: int
    safety_baseline_updated_by: str
    safety_baseline_updated_at: datetime | None
    items: list[AdminAgentResponse]


class AgentUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=300)
    icon: str = Field(min_length=1, max_length=20)
    color: str = Field(min_length=1, max_length=20)
    greeting: str = Field(min_length=1, max_length=300)
    tts_voice: str | None = Field(default=None, max_length=100)
    tools: list[
        Literal[
            "music_recognition",
            "web_search",
            "image_search",
            "image_understanding",
        ]
    ] = Field(
        default_factory=list,
        max_length=10,
    )
    permissions: list[Literal["supervised_outdoor_safety"]] = Field(
        default_factory=list,
        max_length=10,
    )
    enabled: bool
    sort_order: int = Field(ge=0, le=10_000)

    @field_validator(
        "display_name",
        "description",
        "icon",
        "color",
        "greeting",
        mode="before",
    )
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("tts_voice", mode="before")
    @classmethod
    def normalize_voice(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None

    @field_validator("tools", "permissions")
    @classmethod
    def deduplicate_tools(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class CreateAgentRevisionRequest(BaseModel):
    system_prompt: str = Field(min_length=40, max_length=20_000)

    @field_validator("system_prompt", mode="before")
    @classmethod
    def reject_blank_prompt(cls, value: str) -> str:
        return value.strip()


class UpdateSafetyBaselineRequest(BaseModel):
    system_prompt: str = Field(min_length=100, max_length=20_000)

    @field_validator("system_prompt", mode="before")
    @classmethod
    def reject_blank_prompt(cls, value: str) -> str:
        return value.strip()


class SafetyBaselineRevisionResponse(BaseModel):
    id: uuid.UUID
    version: int
    system_prompt: str
    created_by: str
    created_at: datetime
