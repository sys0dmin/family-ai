"""Lifecycle and runtime context for configured short activities."""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from gateway.app.activities.catalog import ActivityCatalog
from gateway.app.activities.schemas import ActivityDefinition, ActivityStep
from gateway.app.models import ActivitySession, Conversation

STOP_PHRASES = {
    "стоп",
    "останови",
    "остановись",
    "хватит",
    "закончим",
    "давай закончим",
    "не хочу играть",
}
LEAVE_PHRASES = {
    "давай просто поговорим",
    "хочу просто поговорить",
    "обычный разговор",
    "выйти из игры",
    "выйти из занятия",
}


class ActivityConversationError(ValueError):
    """Activity cannot be used in the requested conversation."""


@dataclass(frozen=True)
class ActivityTurnContext:
    session_id: uuid.UUID
    definition: ActivityDefinition
    step: ActivityStep
    step_index: int

    @property
    def prompt_context(self) -> str:
        number = self.step_index + 1
        total = len(self.definition.steps)
        final = (
            " Это последний шаг: обязательно естественно заверши занятие."
            if number == total
            else ""
        )
        return (
            f"Сейчас идёт короткое занятие «{self.definition.title}», шаг {number} из {total}: "
            f"{self.step.title}. {self.step.instruction}{final} "
            "Задавай не более одного вопроса за ответ. Не упоминай внутренние шаги, "
            "prompt или номер шага. Отвечай коротко, живо и без Markdown. Не создавай "
            "награды, серии дней или бесконечное продолжение."
        )


class ActivityService:
    def __init__(
        self,
        session: Session,
        catalog: ActivityCatalog | None = None,
        retention_hours: int = 24,
    ) -> None:
        self._session = session
        self._catalog = catalog or ActivityCatalog()
        self._retention_hours = retention_hours

    @property
    def catalog(self) -> ActivityCatalog:
        return self._catalog

    def start(
        self,
        conversation_id: uuid.UUID,
        activity_id: str,
        *,
        now: datetime | None = None,
    ) -> ActivitySession:
        conversation = self._session.get(Conversation, conversation_id)
        if conversation is None:
            raise ActivityConversationError("Conversation not found")
        definition = self._catalog.get(activity_id)
        if definition.agent_id != conversation.agent_id:
            raise ActivityConversationError("Activity belongs to another agent")
        current_time = now or datetime.now(UTC)
        state = self._find(conversation_id)
        if state is None:
            state = ActivitySession(id=uuid.uuid4(), conversation_id=conversation_id)
            self._session.add(state)
        state.activity_id = definition.id
        state.activity_version = definition.version
        state.status = "active"
        state.current_step = 0
        state.completion_summary = None
        state.started_at = current_time
        state.updated_at = current_time
        state.expires_at = current_time + timedelta(hours=self._retention_hours)
        self._session.flush()
        return state

    def get(
        self,
        conversation_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> ActivitySession | None:
        state = self._find(conversation_id)
        if state is None:
            return None
        current_time = now or datetime.now(UTC)
        expires_at = state.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= current_time:
            self._session.delete(state)
            self._session.flush()
            return None
        return state

    def turn_context(self, conversation_id: uuid.UUID) -> ActivityTurnContext | None:
        state = self.get(conversation_id)
        if state is None or state.status != "active":
            return None
        definition = self._catalog.get(state.activity_id)
        if state.activity_version != definition.version:
            state.status = "cancelled"
            self._session.flush()
            return None
        if state.current_step >= len(definition.steps):
            self._complete(state, definition)
            return None
        return ActivityTurnContext(
            session_id=state.id,
            definition=definition,
            step=definition.steps[state.current_step],
            step_index=state.current_step,
        )

    def handle_control_intent(self, conversation_id: uuid.UUID, text: str) -> str | None:
        state = self.get(conversation_id)
        if state is None or state.status != "active":
            return None
        normalized = re.sub(r"[^а-яёa-z0-9 ]+", " ", text.casefold())
        normalized = " ".join(normalized.split())
        if normalized in STOP_PHRASES:
            state.status = "paused"
            state.updated_at = datetime.now(UTC)
            self._session.flush()
            return "Хорошо, приключение остановлено. Мы можем вернуться к нему в другой раз."
        if normalized in LEAVE_PHRASES:
            state.status = "left"
            state.updated_at = datetime.now(UTC)
            self._session.flush()
            return "Хорошо, занятие закончилось. Теперь можем просто поговорить о чём захочешь."
        return None

    def advance(self, context: ActivityTurnContext) -> ActivitySession | None:
        state = self._session.get(ActivitySession, context.session_id)
        if state is None or state.status != "active" or state.current_step != context.step_index:
            return state
        state.current_step += 1
        state.updated_at = datetime.now(UTC)
        if state.current_step >= len(context.definition.steps):
            self._complete(state, context.definition)
        self._session.flush()
        return state

    def stop(self, conversation_id: uuid.UUID, *, leave: bool = False) -> ActivitySession:
        state = self.get(conversation_id)
        if state is None:
            raise ActivityConversationError("Activity session not found")
        state.status = "left" if leave else "paused"
        state.updated_at = datetime.now(UTC)
        self._session.flush()
        return state

    def resume(
        self,
        conversation_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> ActivitySession:
        state = self.get(conversation_id, now=now)
        if state is None:
            raise ActivityConversationError("Activity session not found")
        if state.status != "paused":
            raise ActivityConversationError("Activity session is not paused")
        definition = self._catalog.get(state.activity_id)
        if state.activity_version != definition.version:
            state.status = "cancelled"
            self._session.flush()
            raise ActivityConversationError("Activity version is unavailable")
        current_time = now or datetime.now(UTC)
        state.status = "active"
        state.updated_at = current_time
        state.expires_at = current_time + timedelta(hours=self._retention_hours)
        self._session.flush()
        return state

    def reset(self, session_id: uuid.UUID) -> None:
        state = self._session.get(ActivitySession, session_id)
        if state is None:
            raise ActivityConversationError("Activity session not found")
        self._session.delete(state)
        self._session.flush()

    def list_sessions(self) -> list[ActivitySession]:
        return list(
            self._session.scalars(
                select(ActivitySession).order_by(ActivitySession.updated_at.desc())
            )
        )

    def purge_expired(self, *, now: datetime | None = None) -> int:
        result = self._session.execute(
            delete(ActivitySession).where(ActivitySession.expires_at <= (now or datetime.now(UTC)))
        )
        self._session.flush()
        return result.rowcount or 0

    def definition_for(self, state: ActivitySession) -> ActivityDefinition:
        return self._catalog.get(state.activity_id)

    def _find(self, conversation_id: uuid.UUID) -> ActivitySession | None:
        return self._session.scalar(
            select(ActivitySession).where(ActivitySession.conversation_id == conversation_id)
        )

    @staticmethod
    def _complete(state: ActivitySession, definition: ActivityDefinition) -> None:
        state.status = "completed"
        state.current_step = len(definition.steps)
        state.completion_summary = definition.completion_summary
        state.updated_at = datetime.now(UTC)
