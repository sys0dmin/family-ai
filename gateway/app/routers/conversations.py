"""Conversation HTTP routes."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from gateway.app.db.session import get_db_session
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
    session: Session = Depends(get_db_session),
) -> MessageResponse:
    """Validate and persist one child or assistant message."""

    service = ConversationService(session)
    message = service.create_message(
        conversation_id=conversation_id,
        role=payload.role,
        content=payload.content,
    )
    return MessageResponse.model_validate(message)
