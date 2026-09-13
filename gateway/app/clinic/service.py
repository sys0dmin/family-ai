"""Deterministic lifecycle for the pretend-clinic game."""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from gateway.app.clinic.catalog import ClinicCaseCatalog
from gateway.app.clinic.schemas import ClinicAction, ClinicCase
from gateway.app.models.clinic_session import ClinicProcedureEvent, ClinicSession
from gateway.app.models.conversation import Conversation

CLINIC_AGENT_ID = "clinic_guide"
REAL_HEALTH_PATTERN = re.compile(
    r"\b(?:мне|меня|я|у меня)\b.{0,55}(?:больн|болит|плохо|кров|тошн|"
    r"кружит\w* голов|не могу дышать|тяжело дышать|температур|"
    r"съел\w* таблет|выпил\w* лекар|проглотил\w* таблет|обж[её]г|"
    r"порезал\w*|ударил\w*|сломал\w*)",
    re.IGNORECASE,
)
REAL_HEALTH_RESPONSE = (
    "Стоп, это уже не игра. Пожалуйста, прямо сейчас позови маму, папу или другого "
    "взрослого и расскажи, что случилось. Если трудно дышать, много крови или очень "
    "плохо, взрослому нужно немедленно вызвать экстренную помощь."
)


class ClinicConversationError(ValueError):
    """Clinic game cannot be used in this conversation or state."""


@dataclass(frozen=True)
class ClinicActionResult:
    session: ClinicSession
    action: ClinicAction
    created: bool
    response: str


@dataclass(frozen=True)
class ClinicTurnContext:
    case: ClinicCase
    session: ClinicSession

    @property
    def prompt_context(self) -> str:
        completed = {event.action_id for event in self.session.procedure_events}
        completed_labels = [action.label for action in self.case.actions if action.id in completed]
        remaining_labels = [
            action.label for action in self.case.actions if action.id not in completed
        ]
        return (
            f"Сейчас идёт безопасная ролевая игра в больницу с вымышленным пациентом "
            f"{self.case.patient_name}. Выполнено: {', '.join(completed_labels) or 'ничего'}. "
            f"Осталось: {', '.join(remaining_labels) or 'всё выполнено'}. "
            "Не назначай процедуры и не меняй показатели словами. Предлагай нажимать "
            "только видимые кнопки игровой палаты. Не называй диагноз, лекарство или дозу. "
            "Напоминай, что настоящие процедуры выполняют взрослые медики."
        )


class ClinicGameService:
    def __init__(
        self,
        session: Session,
        catalog: ClinicCaseCatalog | None = None,
        retention_hours: int = 24,
    ) -> None:
        self._session = session
        self._catalog = catalog or ClinicCaseCatalog()
        self._retention_hours = retention_hours

    @property
    def catalog(self) -> ClinicCaseCatalog:
        return self._catalog

    def start(self, conversation_id: uuid.UUID, case_id: str) -> ClinicSession:
        conversation = self._session.get(Conversation, conversation_id)
        if conversation is None:
            raise ClinicConversationError("Conversation not found")
        if conversation.agent_id != CLINIC_AGENT_ID:
            raise ClinicConversationError("Clinic game belongs to another agent")
        definition = self._catalog.get(case_id)
        now = datetime.now(UTC)
        state = self._find(conversation_id)
        if state is None:
            state = ClinicSession(id=uuid.uuid4(), conversation_id=conversation_id)
            self._session.add(state)
        else:
            state.procedure_events.clear()
        state.case_id = definition.id
        state.case_version = definition.version
        state.status = "active"
        state.vital_snapshot = {
            vital.id: vital.model_dump(mode="json") for vital in definition.vitals
        }
        state.started_at = now
        state.updated_at = now
        state.expires_at = now + timedelta(hours=self._retention_hours)
        self._session.flush()
        return state

    def get(self, conversation_id: uuid.UUID) -> ClinicSession | None:
        state = self._find(conversation_id)
        if state is None:
            return None
        expires_at = state.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            self._session.delete(state)
            self._session.flush()
            return None
        return state

    def turn_context(self, conversation_id: uuid.UUID) -> ClinicTurnContext | None:
        state = self.get(conversation_id)
        if state is None or state.status != "active":
            return None
        definition = self._catalog.get(state.case_id)
        if definition.version != state.case_version:
            state.status = "left"
            self._session.flush()
            return None
        return ClinicTurnContext(definition, state)

    def handle_real_health_input(self, conversation_id: uuid.UUID, text: str) -> str | None:
        state = self.get(conversation_id)
        if state is None or state.status != "active" or not REAL_HEALTH_PATTERN.search(text):
            return None
        state.status = "paused"
        state.updated_at = datetime.now(UTC)
        self._session.flush()
        return REAL_HEALTH_RESPONSE

    def perform_action(self, conversation_id: uuid.UUID, action_id: str) -> ClinicActionResult:
        state = self.get(conversation_id)
        if state is None:
            raise ClinicConversationError("Clinic session not found")
        if state.status != "active":
            raise ClinicConversationError("Clinic session is not active")
        definition = self._catalog.get(state.case_id)
        action = next((item for item in definition.actions if item.id == action_id), None)
        if action is None:
            raise ClinicConversationError("Clinic action is unavailable")
        existing = next(
            (event for event in state.procedure_events if event.action_id == action_id),
            None,
        )
        if existing is not None:
            return ClinicActionResult(state, action, False, "Эта отметка уже есть в карточке.")
        self._session.add(
            ClinicProcedureEvent(
                id=uuid.uuid4(),
                session=state,
                action_id=action.id,
            )
        )
        snapshot = {key: dict(value) for key, value in state.vital_snapshot.items()}
        for update in action.updates:
            snapshot[update.vital_id]["value"] = update.value
            snapshot[update.vital_id]["state"] = update.state
        state.vital_snapshot = snapshot
        state.updated_at = datetime.now(UTC)
        completed = {event.action_id for event in state.procedure_events}
        completed.add(action.id)
        response = action.response
        if set(definition.required_action_ids).issubset(completed):
            state.status = "completed"
            response = f"{response} {definition.completion_text}"
        self._session.flush()
        return ClinicActionResult(state, action, True, response)

    def set_status(self, conversation_id: uuid.UUID, status: str) -> ClinicSession:
        state = self.get(conversation_id)
        if state is None:
            raise ClinicConversationError("Clinic session not found")
        allowed = {"pause": "paused", "resume": "active", "leave": "left"}
        if status not in allowed:
            raise ClinicConversationError("Unknown clinic transition")
        if status == "resume" and state.status != "paused":
            raise ClinicConversationError("Clinic session is not paused")
        state.status = allowed[status]
        now = datetime.now(UTC)
        state.updated_at = now
        if status == "resume":
            state.expires_at = now + timedelta(hours=self._retention_hours)
        self._session.flush()
        return state

    def reset(self, session_id: uuid.UUID) -> None:
        state = self.get_by_id(session_id)
        if state is None:
            raise ClinicConversationError("Clinic session not found")
        self._session.delete(state)
        self._session.flush()

    def get_by_id(self, session_id: uuid.UUID) -> ClinicSession | None:
        """Return a session for protected operational controls."""

        return self._session.get(ClinicSession, session_id)

    def list_sessions(self) -> list[ClinicSession]:
        return list(
            self._session.scalars(select(ClinicSession).order_by(ClinicSession.updated_at.desc()))
        )

    def purge_expired(self) -> int:
        result = self._session.execute(
            delete(ClinicSession).where(ClinicSession.expires_at <= datetime.now(UTC))
        )
        self._session.flush()
        return result.rowcount or 0

    def definition_for(self, state: ClinicSession) -> ClinicCase:
        return self._catalog.get(state.case_id)

    def _find(self, conversation_id: uuid.UUID) -> ClinicSession | None:
        return self._session.scalar(
            select(ClinicSession).where(ClinicSession.conversation_id == conversation_id)
        )
