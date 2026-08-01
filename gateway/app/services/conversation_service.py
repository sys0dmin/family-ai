"""Conversation persistence logic."""

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gateway.app.activities import ActivityService, ActivityTurnContext
from gateway.app.agents import ActiveAgent, build_agent_system_message
from gateway.app.constants import LERA_PROFILE_ID
from gateway.app.memory import MemoryService
from gateway.app.models import ChildProfile, Conversation, Message, MessageRole
from gateway.app.providers.contracts import ChatProvider
from gateway.app.providers.schemas import ChatMessage, ChatRequest, ProviderRole, ProviderTool
from gateway.app.safety.contracts import PolicyAction
from gateway.app.services.agent_service import AgentService
from gateway.app.services.safety_service import SafetyService
from gateway.app.services.turn_diagnostics import TurnDiagnostics
from gateway.app.services.visual_media_service import VisualMediaService

logger = logging.getLogger(__name__)

CONTINUING_CONVERSATION_CONTEXT = (
    "Это продолжение уже начатого разговора с Лерой. Не здоровайся заново, не "
    "представляйся повторно и не начинай беседу с чистого листа. Учитывай последние "
    "реплики. Если Лера исправляет твою ошибку, коротко признай поправку, поблагодари "
    "и продолжай с учётом верного факта."
)
UNVERIFIED_MUSIC_TEXT_CONTEXT = (
    "В этом текстовом ходе инструмент распознавания музыки не возвращал результата. "
    "Если доступен веб-поиск, обязательно используй его для проверки фрагмента перед "
    "ответом. "
    "Не выдавай догадку языковой модели за распознанную песню и не выдумывай "
    "правдоподобные названия, исполнителей или источники. Назови ровно одну песню "
    "только при высокой уверенности, что все данные совпадают; иначе честно попроси "
    "ещё одну строку или голосовой напев."
)
SUPERVISED_OUTDOOR_CONTEXT = (
    "Этот агент может обсуждать походную безопасность, но это не разрешение "
    "ребёнку выполнять опасную часть. Всегда давай полезный ответ и явно разделяй "
    "роли. Ребёнок не берёт, не достаёт и не держит спички, нож, точило, крючок или горячую "
    "посуду — это делает взрослый. Не давай ребёнку углы заточки и не учи его проверять остроту. "
    "Отвечай обычным текстом без Markdown."
)

MAX_RESUMED_MESSAGES = 100


@dataclass(frozen=True)
class ConversationHistory:
    """A bounded transcript used to resume one agent conversation."""

    conversation: Conversation | None
    messages: tuple[Message, ...] = ()
    truncated: bool = False


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
        )

    async def generate_ai_response(
        self,
        conversation_id: uuid.UUID,
        runtime_context: str | None = None,
        input_safety_context: str | None = None,
        diagnostics: TurnDiagnostics | None = None,
    ) -> Message:
        """Generate an AI response based on conversation history with safety checks."""

        if not self._provider:
            raise RuntimeError("AI Provider is not configured")

        # 1. Get history
        history = self.get_messages_for_conversation(conversation_id)
        if not history:
            raise RuntimeError("No messages in conversation")

        active_agent = self.get_conversation_agent(conversation_id)
        last_child_msg = next((m for m in reversed(history) if m.role == 'child'), None)
        activity_context: ActivityTurnContext | None = (
            self._activities.turn_context(conversation_id)
            if self._activities
            else None
        )

        # 2. Safety check: Incoming
        if self._safety and last_child_msg:
            input_outcome = (
                self._safety.evaluate_multimodal_input(
                    last_child_msg.content,
                    input_safety_context,
                    active_agent.permissions,
                )
                if input_safety_context
                else self._safety.evaluate_input(
                    last_child_msg.content,
                    active_agent.permissions,
                )
            )
            if input_outcome.action is PolicyAction.BLOCK:
                return self.create_message(
                    conversation_id=conversation_id,
                    role='assistant',
                    content=(
                        input_outcome.safe_response
                        or "Давай поговорим о чём-нибудь другом?"
                    ),
                )
            if input_outcome.action is PolicyAction.TRANSFORM:
                return self.create_message(
                    conversation_id=conversation_id,
                    role='assistant',
                    content=input_outcome.text,
                )

        # 3. Build request for AI
        messages = [
            build_agent_system_message(
                active_agent.system_prompt,
                self._agents.get_safety_baseline(),
            )
        ]
        if self._memory:
            memory_context = self._memory.build_prompt_context(
                self._conversation_profile_id(conversation_id)
            )
            if memory_context:
                messages.append(
                    ChatMessage(
                        role=ProviderRole.SYSTEM,
                        content=memory_context,
                    )
                )
        if runtime_context:
            messages.append(ChatMessage(role=ProviderRole.SYSTEM, content=runtime_context))
        if activity_context:
            messages.append(
                ChatMessage(
                    role=ProviderRole.SYSTEM,
                    content=activity_context.prompt_context,
                )
            )
        if "music_recognition" in active_agent.tools:
            messages.append(
                ChatMessage(
                    role=ProviderRole.SYSTEM,
                    content=UNVERIFIED_MUSIC_TEXT_CONTEXT,
                )
            )
        outdoor_permission = None
        if (
            self._safety
            and "supervised_outdoor_safety" in active_agent.permissions
        ):
            outdoor_permission = self._safety.evaluate_permission(
                "supervised_outdoor_safety",
                active_agent.permissions,
            )
        if outdoor_permission and outdoor_permission.action is PolicyAction.ALLOW:
            messages.append(
                ChatMessage(
                    role=ProviderRole.SYSTEM,
                    content=SUPERVISED_OUTDOOR_CONTEXT,
                )
            )
        if any(message.role == MessageRole.ASSISTANT for message in history):
            messages.append(
                ChatMessage(
                    role=ProviderRole.SYSTEM,
                    content=CONTINUING_CONVERSATION_CONTEXT,
                )
            )
        for msg in history[-10:]:
            role = ProviderRole.USER if msg.role == 'child' else ProviderRole.ASSISTANT
            messages.append(ChatMessage(role=role, content=msg.content))

        web_search_policy = None
        if self._safety and "web_search" in active_agent.tools:
            web_search_policy = self._safety.evaluate_tool(
                "web_search",
                active_agent.tools,
            )
        tools = (
            (ProviderTool.WEB_SEARCH,)
            if web_search_policy and web_search_policy.action is PolicyAction.ALLOW
            else ()
        )
        request = ChatRequest(messages=messages, tools=tools)

        # 4. Call AI
        llm_started_at = time.perf_counter()
        try:
            response = await self._provider.generate_response(request)
        finally:
            if diagnostics is not None:
                diagnostics.llm_duration_ms = round(
                    (time.perf_counter() - llm_started_at) * 1000
                )
        response_content = response.content.replace('\x00', '')

        # 5. Safety check: Outgoing
        if self._safety:
            output_outcome = self._safety.evaluate_output(
                response_content,
                active_agent.permissions,
            )
            response_content = output_outcome.text
            if output_outcome.action is PolicyAction.BLOCK:
                primary = output_outcome.primary_decision
                logger.warning(
                    "unsafe_model_response_blocked",
                    extra={
                        "agent_id": active_agent.id,
                        "conversation_id": str(conversation_id),
                        "rule_id": primary.rule_id,
                        "reason": primary.reason,
                    },
                )
                return self.create_message(
                    conversation_id=conversation_id,
                    role='assistant',
                    content=output_outcome.safe_response or "Давай сменим тему?",
                )

        # 6. Store and return response
        message = self.create_message(
            conversation_id=conversation_id,
            role='assistant',
            content=response_content,
        )
        if self._activities and activity_context:
            self._activities.advance(activity_context)
        if self._visual_media and last_child_msg:
            await self._visual_media.attach_for_turn(
                message=message,
                agent=active_agent,
                child_text=last_child_msg.content,
            )
        return message

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
