import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from gateway.app.dependencies import get_conversation_service
from gateway.app.schemas.conversations import (
    ConversationHistoryResponse,
    CreateConversationRequest,
    CreateConversationResponse,
    CreateMessageRequest,
    MessageResponse,
)
from gateway.app.services.agent_service import AgentNotFoundError
from gateway.app.services.conversation_service import ConversationService


def normalize_role(role_str: str) -> str:
    """Convert string role to lowercase string."""
    role_lower = role_str.lower()
    if role_lower in {"child", "assistant"}:
        return role_lower
    raise ValueError(f"Invalid role: {role_str}")

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


@router.get(
    "/latest",
    response_model=ConversationHistoryResponse,
    summary="Resume the latest retained conversation for one agent",
)
def get_latest_conversation(
    agent_id: str = Query(min_length=1, max_length=50),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationHistoryResponse:
    """Return only this agent's recent session for the child interface."""

    try:
        history = service.get_latest_history_for_agent(agent_id)
    except AgentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent is unavailable",
        ) from exc
    return ConversationHistoryResponse(
        conversation_id=history.conversation.id if history.conversation else None,
        agent_id=agent_id,
        messages=[MessageResponse.model_validate(message) for message in history.messages],
        history_truncated=history.truncated,
    )


@router.get(
    "/{conversation_id}/messages/{message_id}",
    response_model=MessageResponse,
    summary="Get one stored conversation message",
)
def get_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    service: ConversationService = Depends(get_conversation_service),
) -> MessageResponse:
    message = service.get_message(conversation_id, message_id)
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return MessageResponse.model_validate(message)


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
    payload: CreateConversationRequest | None = None,
    service: ConversationService = Depends(get_conversation_service),
) -> CreateConversationResponse:
    try:
        conversation = service.create_conversation(payload.agent_id if payload else None)
    except AgentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent is unavailable",
        ) from exc
    return CreateConversationResponse(
        conversation_id=conversation.id,
        agent_id=conversation.agent_id,
    )
