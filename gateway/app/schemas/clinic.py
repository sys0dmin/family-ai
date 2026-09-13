"""Public contracts for the deterministic pretend-clinic game."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from gateway.app.schemas.conversations import MessageResponse


class ClinicCaseSummaryResponse(BaseModel):
    id: str
    version: int
    title: str
    short_title: str
    description: str
    patient_name: str
    patient_icon: str
    color: str


class ClinicCaseListResponse(BaseModel):
    schema_version: int
    items: list[ClinicCaseSummaryResponse]


class ClinicVitalResponse(BaseModel):
    id: str
    icon: str
    label: str
    value: str
    unit: str
    state: str


class ClinicActionResponse(BaseModel):
    id: str
    icon: str
    label: str
    completed: bool


class ClinicSessionResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    case_id: str
    case_version: int
    title: str
    patient_name: str
    patient_icon: str
    color: str
    status: str
    is_pretend: bool = True
    vitals: list[ClinicVitalResponse]
    actions: list[ClinicActionResponse]
    started_at: datetime
    updated_at: datetime
    expires_at: datetime


class ClinicStateResponse(BaseModel):
    session: ClinicSessionResponse | None


class ClinicTurnResponse(BaseModel):
    session: ClinicSessionResponse
    message: MessageResponse
    repeated: bool = False
