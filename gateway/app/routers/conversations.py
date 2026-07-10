"""Conversation HTTP routes."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from gateway.app.dependencies import get_conversation_service
from gateway.app.models import MessageRole
from gateway.app.schemas.conversations import CreateMessageRequest, MessageResponse
from gateway.app.services.conversation_service import ConversationService

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    summary="Store a transcript line in a conversation",
)
def create_message(
    conversation_id: uuid.UUID,
    payload: CreateMessageRequest,
    service: ConversationService = Depends(get_conversation_service),
) -> MessageResponse:
    """Validate and persist one child or assistant message."""

    message = service.create_message(
        conversation_id=conversation_id,
        role=payload.role,
        content=payload.content,
    )
    return MessageResponse.model_validate(message)


@router.post(
    "/{conversation_id}/turn",
    response_model=MessageResponse,
    summary="Process a child message and get an AI response",
)
async def process_turn(
    conversation_id: uuid.UUID,
    payload: CreateMessageRequest,
    service: ConversationService = Depends(get_conversation_service),
) -> MessageResponse:
    """Store child message and generate assistant response."""

    # 1. Store child message
    service.create_message(
        conversation_id=conversation_id,
        role=MessageRole.CHILD,
        content=payload.content,
    )

    # 2. Generate and store AI response
    assistant_message = await service.generate_ai_response(conversation_id)

    return MessageResponse.model_validate(assistant_message)
