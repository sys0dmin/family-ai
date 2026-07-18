import uuid

from fastapi import APIRouter, Depends

from gateway.app.dependencies import get_conversation_service
from gateway.app.schemas.conversations import (
    CreateConversationResponse,
    CreateMessageRequest,
    MessageResponse,
)
from gateway.app.services.conversation_service import ConversationService


def normalize_role(role_str: str) -> str:
    """Convert string role to lowercase string."""
    role_lower = role_str.lower()
    if role_lower in {"child", "assistant"}:
        return role_lower
    raise ValueError(f"Invalid role: {role_str}")

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
        role=normalize_role(payload.role),
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

    if normalize_role(payload.role) != "child":
        raise ValueError("Only child messages can start an AI turn")
    assistant_message = await service.process_turn(conversation_id, payload.content)

    return MessageResponse.model_validate(assistant_message)


@router.post(
    "/",
    response_model=CreateConversationResponse,
    summary="Create new conversation for Лера",
)
def create_conversation(
    service: ConversationService = Depends(get_conversation_service),
) -> CreateConversationResponse:
    conversation = service.create_conversation()
    return CreateConversationResponse(conversation_id=conversation.id)
