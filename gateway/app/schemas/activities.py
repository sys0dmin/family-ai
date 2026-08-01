"""Public contracts for configured short activities."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from gateway.app.schemas.conversations import MessageResponse


class ActivitySummaryResponse(BaseModel):
    id: str
    version: int
    agent_id: str
    title: str
    short_title: str
    description: str
    icon: str
    color: str
    total_steps: int


class ActivityListResponse(BaseModel):
    schema_version: int
    items: list[ActivitySummaryResponse]


class ActivitySessionResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    activity_id: str
    activity_version: int
    title: str
    icon: str
    color: str
    status: str
    current_step: int
    total_steps: int
    current_step_title: str | None
    current_step_icon: str | None
    completion_summary: str | None
    started_at: datetime
    updated_at: datetime
    expires_at: datetime


class ActivityStateResponse(BaseModel):
    session: ActivitySessionResponse | None


class ActivityStartResponse(BaseModel):
    session: ActivitySessionResponse
    message: MessageResponse


class ActivityStopRequest(BaseModel):
    leave_for_conversation: bool = False


class ActivityStopResponse(BaseModel):
    session: ActivitySessionResponse
    message: MessageResponse


class ActivityAdminStepResponse(BaseModel):
    id: str
    icon: str
    title: str
    instruction: str


class ActivityAdminDefinitionResponse(ActivitySummaryResponse):
    opening_text: str
    completion_summary: str
    steps: list[ActivityAdminStepResponse] = Field(default_factory=list)


class ActivityAdminCatalogResponse(BaseModel):
    schema_version: int
    items: list[ActivityAdminDefinitionResponse]


class ActivityAdminSessionsResponse(BaseModel):
    items: list[ActivitySessionResponse]
