"""Protected contracts for parent feedback and confirmed regression cases."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from gateway.app.models import FeedbackReason


class ExpectedTechnicalError(StrEnum):
    NONE = "none"
    PROVIDER_ERROR = "provider_error"


class FeedbackWriteRequest(BaseModel):
    message_id: uuid.UUID
    reason: FeedbackReason
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("note", mode="before")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None


class FeedbackResponse(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    reason: FeedbackReason
    note: str | None
    created_at: datetime
    updated_at: datetime


class FeedbackReasonCount(BaseModel):
    reason: FeedbackReason
    count: int


class QualitySummaryResponse(BaseModel):
    days: int
    total_feedback: int
    regression_cases: int
    reasons: list[FeedbackReasonCount]


class RegressionCasePreviewResponse(BaseModel):
    source_feedback_id: uuid.UUID
    agent_id: str
    title: str
    prompt: str
    expected_response: str
    expected_safety_status: Literal["passed", "guardrail", "blocked"] = "passed"
    expected_safety_rule_id: str | None = None
    expected_technical_error: ExpectedTechnicalError = ExpectedTechnicalError.NONE


class RegressionCaseWriteRequest(BaseModel):
    confirmed: Literal[True]
    source_feedback_id: uuid.UUID | None = None
    agent_id: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=2, max_length=160)
    prompt: str = Field(min_length=1, max_length=4000)
    expected_response: str = Field(min_length=1, max_length=8000)
    expected_safety_status: Literal["passed", "guardrail", "blocked"]
    expected_safety_rule_id: str | None = Field(default=None, max_length=120)
    expected_technical_error: ExpectedTechnicalError = ExpectedTechnicalError.NONE

    @field_validator("agent_id", "title", "prompt", "expected_response", mode="before")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("expected_safety_rule_id", mode="before")
    @classmethod
    def normalize_rule_id(cls, value: str | None) -> str | None:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None


class RegressionCaseResponse(BaseModel):
    id: uuid.UUID
    source_feedback_id: uuid.UUID | None
    agent_id: str
    title: str
    prompt: str
    expected_response: str
    expected_safety_status: str
    expected_safety_rule_id: str | None
    expected_technical_error: str
    created_at: datetime
    updated_at: datetime


class RegressionCaseListResponse(BaseModel):
    items: list[RegressionCaseResponse]
    total: int


class RegressionComparison(BaseModel):
    response_matches: bool
    safety_status_matches: bool
    safety_rule_matches: bool
    technical_error_matches: bool
    overall_matches: bool


class RegressionRunResponse(BaseModel):
    case_id: uuid.UUID
    actual_response: str
    actual_safety_status: str | None
    actual_safety_rule_id: str | None
    actual_technical_error: ExpectedTechnicalError
    llm_duration_ms: int | None
    comparison: RegressionComparison
