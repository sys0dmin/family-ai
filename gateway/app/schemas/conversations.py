"""Pydantic schemas for conversation endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from gateway.app.models.message import MessageRole


class CreateMessageRequest(BaseModel):
    """Incoming payload for a new transcript line."""

    role: MessageRole
    content: str = Field(min_length=1, max_length=8000)


class MessageResponse(BaseModel):
    """Stored message returned to API clients."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: MessageRole
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}
