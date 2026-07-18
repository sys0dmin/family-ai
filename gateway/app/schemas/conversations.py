"""Pydantic schemas for conversation endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateMessageRequest(BaseModel):
    """Incoming payload for a new transcript line."""

    role: str
    content: str = Field(min_length=1, max_length=8000)


class CreateConversationRequest(BaseModel):
    """Optional agent selection for a new isolated conversation."""

    agent_id: str = Field(default="teacher_friend", min_length=1, max_length=50)


class CreateConversationResponse(BaseModel):
    """Response payload for newly created conversations."""

    conversation_id: uuid.UUID
    agent_id: str


class MessageResponse(BaseModel):
    """Stored message returned to API clients."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}
