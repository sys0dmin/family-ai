"""Protected Admin API schemas for parent-managed memory."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from gateway.app.models import MemoryCategory, MemorySourceType


class MemoryWriteRequest(BaseModel):
    category: MemoryCategory
    topic: str = Field(min_length=2, max_length=120)
    summary: str = Field(min_length=3, max_length=1000)
    source_type: MemorySourceType
    source_date: date
    source_note: str | None = Field(default=None, max_length=500)

    @field_validator("topic", "summary", mode="before")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("source_note", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @field_validator("source_date")
    @classmethod
    def reject_future_source_date(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("source_date cannot be in the future")
        return value


class MemoryResponse(BaseModel):
    id: uuid.UUID
    category: MemoryCategory
    topic: str
    summary: str
    source_type: MemorySourceType
    source_date: date
    source_note: str | None
    created_by: str
    updated_by: str
    confirmed_at: datetime
    created_at: datetime
    updated_at: datetime


class MemoryListResponse(BaseModel):
    items: list[MemoryResponse]
    total: int
