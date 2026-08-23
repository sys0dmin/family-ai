"""Conversation persistence logic."""

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gateway.app.activities import ActivityService, ActivityTurnContext
from gateway.app.agents import ActiveAgent
from gateway.app.constants import LERA_PROFILE_ID
from gateway.app.memory import MemoryService
from gateway.app.models import ChildProfile, Conversation, Message, MessageRole
from gateway.app.providers.contracts import ChatProvider
from gateway.app.providers.schemas import ChatRequest
from gateway.app.safety.contracts import PolicyAction
from gateway.app.services.agent_service import AgentService
from gateway.app.services.conversation_prompt import (
    ConversationPromptContext,
    build_conversation_request,
)
from gateway.app.services.safety_service import SafetyService
from gateway.app.services.turn_diagnostics import TurnDiagnostics
from gateway.app.services.visual_media_service import VisualMediaService

logger = logging.getLogger(__name__)

MAX_RESUMED_MESSAGES = 100


@dataclass(frozen=True)
class ConversationHistory:
    """A bounded transcript used to resume one agent conversation."""

    conversation: Conversation | None
    messages: tuple[Message, ...] = ()
    truncated: bool = False


@dataclass(frozen=True)
class PreparedConversationTurn:
    """Context loaded once and shared by every stage of one generated turn."""

    history: tuple[Message, ...]
    active_agent: ActiveAgent
    last_child_message: Message | None
    activity_context: ActivityTurnContext | None


@dataclass(frozen=True)
class EvaluatedOutput:
    """Normalized model text and whether policy blocked the original output."""

    content: str
    blocked: bool = False


class ConversationService:
    """Create conversations and store transcript lines."""

    def __init__(
        self,
        session: Session,
        provider: ChatProvider | None = None,
        safety: SafetyService | None = None,
        agents: AgentService | None = None,
        visual_media: VisualMediaService | None = None,
        default_agent_id: str = "teacher_friend",
        retention_days: int = 10,
        memory: MemoryService | None = None,
        activities: ActivityService | None = None,
    ) -> None:
        self._session = session
        self._provider = provider
        self._safety = safety
        self._agents = agents
        self._visual_media = visual_media
        self._default_agent_id = default_agent_id
        self._retention_days = retention_days
        self._memory = memory
        self._activities = activities

    def create_message(
        self,
        conversation_id: uuid.UUID,
        role: str | MessageRole,
        content: str,
    ) -> Message:
        """Store a message, creating the conversation when needed."""

        conversation = self._get_or_create_conversation(conversation_id)

        # Normalize role to lowercase string
        if isinstance(role, MessageRole):
            role_value = role.value
        else:
            role_value = role.lower() if isinstance(role, str) else str(role)

        message = Message(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            role=role_value,
            content=content,
            created_at=datetime.now(UTC),
        )
        self._session.add(message)
        self._session.flush()
        return message

    async def process_turn(
        self,
        conversation_id: uuid.UUID,
        text: str,
        runtime_context: str | None = None,
        input_safety_context: str | None = None,
        diagnostics: TurnDiagnostics | None = None,
        request_id: uuid.UUID | None = None,
    ) -> Message:
        """Store a child message and return the generated assistant response."""

        self.create_message(
            conversation_id=conversation_id,
            role=MessageRole.CHILD,
            content=text,
        )
        if self._activities:
            control_response = self._activities.handle_control_intent(
                conversation_id,
                text,
            )
            if control_response:
                return self.create_message(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT,
                    content=control_response,
                )
        return await self.generate_ai_response(
            conversation_id,
            runtime_context=runtime_context,
            input_safety_context=input_safety_context,
            diagnostics=diagnostics,
            request_id=request_id,
        )

    async def generate_ai_response(
        self,
        conversation_id: uuid.UUID,
        runtime_context: str | None = None,
        input_safety_context: str | None = None,
        diagnostics: TurnDiagnostics | None = None,
        request_id: uuid.UUID | None = None,
    ) -> Message:
        """Generate an AI response based on conversation history with safety checks."""

        if not self._provider:
            raise RuntimeError("AI Provider is not configured")

        turn = self._prepare_generated_turn(conversation_id)
        input_policy_response = self._evaluate_turn_input(
            turn,
            input_safety_context=input_safety_context,
        )
        if input_policy_response is not None:
            return self.create_message(
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content=input_policy_response,
            )

        request = self._build_chat_request(
            conversation_id,
            turn,
            runtime_context=runtime_context,
            request_id=request_id,
        )
        response_content = await self._generate_provider_content(request, diagnostics)
        evaluated_output = self._evaluate_turn_output(
            response_content,
            conversation_id=conversation_id,
            active_agent=turn.active_agent,
        )
        message = self.create_message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=evaluated_output.content,
        )
        if evaluated_output.blocked:
            return message

        await self._complete_generated_turn(message, turn)
        return message

    def _prepare_generated_turn(
        self,
        conversation_id: uuid.UUID,
    ) -> PreparedConversationTurn:
        history = self.get_messages_for_conversation(conversation_id)
        if not history:
            raise RuntimeError("No messages in conversation")
        return PreparedConversationTurn(
            history=tuple(history),
            active_agent=self.get_conversation_agent(conversation_id),
            last_child_message=next(
                (message for message in reversed(history) if message.role == MessageRole.CHILD),
                None,
            ),
            activity_context=(
                self._activities.turn_context(conversation_id) if self._activities else None
            ),
        )

    def _evaluate_turn_input(
        self,
        turn: PreparedConversationTurn,
        *,
        input_safety_context: str | None,
    ) -> str | None:
        child_message = turn.last_child_message
        if not self._safety or child_message is None:
            return None
        outcome = (
            self._safety.evaluate_multimodal_input(
                child_message.content,
                input_safety_context,
                turn.active_agent.permissions,
            )
            if input_safety_context
            else self._safety.evaluate_input(
                child_message.content,
                turn.active_agent.permissions,
            )
        )
        if outcome.action is PolicyAction.BLOCK:
            return outcome.safe_response or "Давай поговорим о чём-нибудь другом?"
        if outcome.action is PolicyAction.TRANSFORM:
            return outcome.text
        return None

    def _build_chat_request(
        self,
        conversation_id: uuid.UUID,
        turn: PreparedConversationTurn,
        *,
        runtime_context: str | None,
        request_id: uuid.UUID | None,
    ) -> ChatRequest:
        if self._agents is None:
            raise RuntimeError("Agent service is not configured")
        memory_context = None
        if self._memory:
            memory_context = self._memory.build_prompt_context(
                self._conversation_profile_id(conversation_id)
            )
        return build_conversation_request(
            ConversationPromptContext(
                active_agent=turn.active_agent,
                safety_baseline=self._agents.get_safety_baseline(),
                history=turn.history,
                memory_context=memory_context,
                runtime_context=runtime_context,
                activity_context=(
                    turn.activity_context.prompt_context
                    if turn.activity_context
                    else None
                ),
            ),
            self._safety,
            request_id,
        )

    async def _generate_provider_content(
        self,
        request: ChatRequest,
        diagnostics: TurnDiagnostics | None,
    ) -> str:
        if self._provider is None:
            raise RuntimeError("AI Provider is not configured")
        llm_started_at = time.perf_counter()
        try:
            response = await self._provider.generate_response(request)
        finally:
            if diagnostics is not None:
                diagnostics.llm_duration_ms = round((time.perf_counter() - llm_started_at) * 1000)
        return response.content.replace("\x00", "")

    def _evaluate_turn_output(
        self,
        response_content: str,
        *,
        conversation_id: uuid.UUID,
        active_agent: ActiveAgent,
    ) -> EvaluatedOutput:
        if not self._safety:
            return EvaluatedOutput(response_content)
        outcome = self._safety.evaluate_output(
            response_content,
            active_agent.permissions,
        )
        if outcome.action is not PolicyAction.BLOCK:
            return EvaluatedOutput(outcome.text)

        primary = outcome.primary_decision
        logger.warning(
            "unsafe_model_response_blocked",
            extra={
                "agent_id": active_agent.id,
                "conversation_id": str(conversation_id),
                "rule_id": primary.rule_id,
                "reason": primary.reason,
            },
        )
        return EvaluatedOutput(
            outcome.safe_response or "Давай сменим тему?",
            blocked=True,
        )

    async def _complete_generated_turn(
        self,
        message: Message,
        turn: PreparedConversationTurn,
    ) -> None:
        if self._activities and turn.activity_context:
            self._activities.advance(turn.activity_context)
        if self._visual_media and turn.last_child_message:
            await self._visual_media.attach_for_turn(
                message=message,
                agent=turn.active_agent,
                child_text=turn.last_child_message.content,
            )

    def _get_or_create_conversation(self, conversation_id: uuid.UUID) -> Conversation:
        conversation = self._session.get(Conversation, conversation_id)
        if conversation is not None:
            return conversation

        profile = self._session.get(ChildProfile, LERA_PROFILE_ID)
        if profile is None:
            msg = "Child profile is not initialized"
            raise RuntimeError(msg)

        created_at = datetime.now(UTC)
        conversation = Conversation(
            id=conversation_id,
            child_profile_id=LERA_PROFILE_ID,
            started_at=created_at,
            created_at=created_at,
            **self._agent_binding(self._default_agent_id),
        )
        self._session.add(conversation)
        self._session.flush()
        return conversation

    def _conversation_profile_id(self, conversation_id: uuid.UUID) -> uuid.UUID:
        conversation = self._session.get(Conversation, conversation_id)
        if conversation is None:
            raise RuntimeError("Conversation is not initialized")
        return conversation.child_profile_id

    def create_conversation(self, agent_id: str | None = None) -> Conversation:
        """Создать новый диалог и вернуть его идентификатор."""

        profile = self._session.get(ChildProfile, LERA_PROFILE_ID)
        if profile is None:
            raise RuntimeError("Child profile is not initialized")

        created_at = datetime.now(UTC)
        conversation = Conversation(
            id=uuid.uuid4(),
            child_profile_id=LERA_PROFILE_ID,
            started_at=created_at,
            created_at=created_at,
            **self._agent_binding(agent_id or self._default_agent_id),
        )
        self._session.add(conversation)
        self._session.flush()
        return conversation

    def get_conversation_agent(self, conversation_id: uuid.UUID) -> ActiveAgent:
        """Return the exact published agent revision bound to a conversation."""

        if self._agents is None:
            raise RuntimeError("Agent service is not configured")
        conversation = self._session.get(Conversation, conversation_id)
        if conversation is None:
            raise RuntimeError("Conversation is not initialized")
        return self._agents.get_revision(
            conversation.agent_id,
            conversation.agent_revision_id,
        )

    def _agent_binding(self, agent_id: str) -> dict[str, object]:
        if self._agents is None:
            raise RuntimeError("Agent service is not configured")
        agent = self._agents.get_active(agent_id)
        return {
            "agent_id": agent.id,
            "agent_revision_id": uuid.UUID(agent.revision_id),
        }

    def get_messages_for_conversation(self, conversation_id: uuid.UUID) -> list[Message]:
        """Return messages ordered by creation time."""

        statement = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        messages = list(self._session.scalars(statement))

        # Normalize role strings to enum values
        for msg in messages:
            if isinstance(msg.role, str):
                msg.role = MessageRole(msg.role)

        return messages

    def get_latest_history_for_agent(
        self,
        agent_id: str,
        *,
        now: datetime | None = None,
        message_limit: int = MAX_RESUMED_MESSAGES,
    ) -> ConversationHistory:
        """Return the newest retained conversation without mixing agent contexts."""

        if self._agents is None:
            raise RuntimeError("Agent service is not configured")
        self._agents.get_active(agent_id)

        cutoff = (now or datetime.now(UTC)) - timedelta(days=self._retention_days)
        latest_activity = func.coalesce(func.max(Message.created_at), Conversation.created_at)
        conversation_id = self._session.scalar(
            select(Conversation.id)
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .where(
                Conversation.child_profile_id == LERA_PROFILE_ID,
                Conversation.agent_id == agent_id,
            )
            .group_by(Conversation.id, Conversation.created_at)
            .having(latest_activity >= cutoff)
            .order_by(latest_activity.desc(), Conversation.created_at.desc())
            .limit(1)
        )
        if conversation_id is None:
            return ConversationHistory(conversation=None)

        newest_first = list(
            self._session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(message_limit + 1)
            )
        )
        truncated = len(newest_first) > message_limit
        messages = newest_first[:message_limit]
        messages.reverse()
        for message in messages:
            if isinstance(message.role, str):
                message.role = MessageRole(message.role)

        return ConversationHistory(
            conversation=self._session.get(Conversation, conversation_id),
            messages=tuple(messages),
            truncated=truncated,
        )

    def get_message(self, conversation_id: uuid.UUID, message_id: uuid.UUID) -> Message | None:
        """Return one message only when it belongs to the requested conversation."""

        return self._session.scalar(
            select(Message).where(
                Message.id == message_id,
                Message.conversation_id == conversation_id,
            )
        )
