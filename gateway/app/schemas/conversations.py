"""Pydantic schemas for conversation endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateMessageRequest(BaseModel):
    """Incoming payload for a new transcript line."""

    role: str
    content: str = Field(min_length=1, max_length=8000)


class CreateConversationResponse(BaseModel):
    """Response payload for newly created conversations."""

    conversation_id: uuid.UUID


class MessageResponse(BaseModel):
    """Stored message returned to API clients."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}
