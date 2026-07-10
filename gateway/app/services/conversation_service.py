"""Conversation persistence logic."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from gateway.app.agents import get_teacher_friend_system_message
from gateway.app.constants import LERA_PROFILE_ID
from gateway.app.models import ChildProfile, Conversation, Message, MessageRole
from gateway.app.providers.base import AIProvider
from gateway.app.providers.schemas import ChatMessage, ChatRequest, ProviderRole
from gateway.app.services.safety_service import SafetyService


class ConversationService:
    """Create conversations and store transcript lines."""

    def __init__(
        self,
        session: Session,
        provider: AIProvider | None = None,
        safety: SafetyService | None = None,
    ) -> None:
        self._session = session
        self._provider = provider
        self._safety = safety

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

    async def generate_ai_response(
        self,
        conversation_id: uuid.UUID,
    ) -> Message:
        """Generate an AI response based on conversation history with safety checks."""

        if not self._provider:
            raise RuntimeError("AI Provider is not configured")

        # 1. Get history
        history = self.get_messages_for_conversation(conversation_id)
        if not history:
            raise RuntimeError("No messages in conversation")

        last_child_msg = next((m for m in reversed(history) if m.role == MessageRole.CHILD), None)

        # 2. Safety check: Incoming
        if self._safety and last_child_msg:
            safety_result = self._safety.check_text(last_child_msg.content)
            if not safety_result.is_safe:
                return self.create_message(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT,
                    content=safety_result.suggested_response or "Давай поговорим о чём-нибудь другом?",
                )

        # 3. Build request for AI
        messages = [get_teacher_friend_system_message()]
        for msg in history[-10:]:
            role = ProviderRole.USER if msg.role == MessageRole.CHILD else ProviderRole.ASSISTANT
            messages.append(ChatMessage(role=role, content=msg.content))

        request = ChatRequest(messages=messages)

        # 4. Call AI
        response = await self._provider.generate_response(request)

        # 5. Safety check: Outgoing
        if self._safety:
            safety_result = self._safety.check_text(response.content)
            if not safety_result.is_safe:
                return self.create_message(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT,
                    content="Ой, я задумался о чём-то не том. Давай лучше поиграем или спросим у мамы?",
                )

        # 6. Store and return response
        return self.create_message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=response.content,
        )

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
