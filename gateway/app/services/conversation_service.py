"""Conversation persistence logic."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from gateway.app.constants import LERA_PROFILE_ID
from gateway.app.models import ChildProfile, Conversation, Message, MessageRole


class ConversationService:
    """Create conversations and store transcript lines."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_message(
        self,
        conversation_id: uuid.UUID,
        role: MessageRole,
        content: str,
    ) -> Message:
        """Store a message, creating the conversation when needed."""

        conversation = self._get_or_create_conversation(conversation_id)
        message = Message(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            role=role,
            content=content,
        )
        self._session.add(message)
        self._session.flush()
        return message

    def _get_or_create_conversation(self, conversation_id: uuid.UUID) -> Conversation:
        conversation = self._session.get(Conversation, conversation_id)
        if conversation is not None:
            return conversation

        profile = self._session.get(ChildProfile, LERA_PROFILE_ID)
        if profile is None:
            msg = "Child profile is not initialized"
            raise RuntimeError(msg)

        conversation = Conversation(
            id=conversation_id,
            child_profile_id=LERA_PROFILE_ID,
        )
        self._session.add(conversation)
        self._session.flush()
        return conversation

    def get_messages_for_conversation(self, conversation_id: uuid.UUID) -> list[Message]:
        """Return messages ordered by creation time."""

        statement = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        return list(self._session.scalars(statement))
