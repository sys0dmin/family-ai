"""Tests for parent feedback retention and confirmed regression cases."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from gateway.admin.history_service import HistoryService
from gateway.admin.main import _verify_admin
from gateway.admin.main import app as admin_app
from gateway.admin.quality_router import get_quality_service
from gateway.admin.quality_schemas import (
    FeedbackWriteRequest,
    RegressionCaseWriteRequest,
)
from gateway.admin.quality_service import InvalidFeedbackTargetError, QualityService
from gateway.admin.studio_router import get_studio_service
from gateway.admin.studio_schemas import AgentTestResponse
from gateway.app.constants import LERA_PROFILE_ID
from gateway.app.models import (
    Conversation,
    FeedbackReason,
    Message,
    MessageFeedback,
    MessageRole,
    RegressionCase,
)
from gateway.app.services.retention_service import RetentionService

TEACHER_REVISION_ID = uuid.UUID("a0000000-0000-0000-0000-000000000001")


def _conversation_with_turn(
    session: Session,
    *,
    created_at: datetime | None = None,
) -> tuple[Message, Message]:
    timestamp = created_at or datetime.now(UTC)
    conversation = Conversation(
        id=uuid.uuid4(),
        child_profile_id=LERA_PROFILE_ID,
        agent_id="teacher_friend",
        agent_revision_id=TEACHER_REVISION_ID,
        started_at=timestamp,
    )
    child = Message(
        id=uuid.uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.CHILD,
        content="Почему небо голубое?",
        created_at=timestamp,
    )
    assistant = Message(
        id=uuid.uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="Потому что океан отражается в небе.",
        created_at=timestamp + timedelta(seconds=1),
    )
    session.add_all((conversation, child, assistant))
    session.flush()
    return child, assistant


def _feedback(service: QualityService, message: Message):
    return service.upsert_feedback(
        FeedbackWriteRequest(
            message_id=message.id,
            reason=FeedbackReason.FACTUAL_ERROR,
            note="Неверное объяснение рассеяния света",
        )
    )


def test_feedback_is_upserted_without_copying_message_content(
    db_session: Session,
) -> None:
    _child, assistant = _conversation_with_turn(db_session)
    service = QualityService(db_session)

    created = _feedback(service, assistant)
    updated = service.upsert_feedback(
        FeedbackWriteRequest(
            message_id=assistant.id,
            reason=FeedbackReason.TOO_COMPLEX,
            note="  Слишком много терминов  ",
        )
    )

    rows = list(db_session.scalars(select(MessageFeedback)))
    assert len(rows) == 1
    assert created.id == updated.id
    assert updated.reason is FeedbackReason.TOO_COMPLEX
    assert updated.note == "Слишком много терминов"
    assert assistant.content not in str(rows[0].__dict__)
    history = HistoryService(db_session).get_conversations(
        days=10,
        page=1,
        page_size=10,
    )
    assistant_history = next(
        message
        for message in history.items[0].messages
        if message.id == assistant.id
    )
    assert assistant_history.feedback is not None
    assert assistant_history.feedback.reason is FeedbackReason.TOO_COMPLEX


def test_feedback_rejects_child_message(db_session: Session) -> None:
    child, _assistant = _conversation_with_turn(db_session)
    service = QualityService(db_session)

    with pytest.raises(
        InvalidFeedbackTargetError,
        match="Only an assistant reply",
    ):
        service.upsert_feedback(
            FeedbackWriteRequest(
                message_id=child.id,
                reason=FeedbackReason.MISUNDERSTOOD,
            )
        )


def test_regression_case_requires_preview_and_explicit_confirmed_copy(
    db_session: Session,
) -> None:
    child, assistant = _conversation_with_turn(db_session)
    service = QualityService(db_session)
    feedback = _feedback(service, assistant)

    preview = service.preview_regression_case(feedback.id)
    created = service.create_regression_case(
        RegressionCaseWriteRequest(
            confirmed=True,
            source_feedback_id=preview.source_feedback_id,
            agent_id=preview.agent_id,
            title="Голубое небо",
            prompt=child.content,
            expected_response="Синий свет сильнее рассеивается в атмосфере.",
            expected_safety_status="passed",
            expected_technical_error="none",
        )
    )

    assert preview.prompt == child.content
    assert preview.expected_response == assistant.content
    assert created.source_feedback_id == feedback.id
    assert created.expected_response.startswith("Синий свет")


def test_retention_deletes_feedback_but_keeps_confirmed_case(
    db_session: Session,
) -> None:
    old = datetime.now(UTC) - timedelta(days=11)
    child, assistant = _conversation_with_turn(db_session, created_at=old)
    service = QualityService(db_session)
    feedback = _feedback(service, assistant)
    case = service.create_regression_case(
        RegressionCaseWriteRequest(
            confirmed=True,
            source_feedback_id=feedback.id,
            agent_id="teacher_friend",
            title="Retained explicit test",
            prompt=child.content,
            expected_response="Безопасный ожидаемый ответ",
            expected_safety_status="passed",
            expected_technical_error="none",
        )
    )

    deleted = RetentionService(db_session, retention_days=10).purge_expired_messages()
    db_session.expire_all()

    assert deleted == 2
    assert db_session.get(MessageFeedback, feedback.id) is None
    retained = db_session.get(RegressionCase, case.id)
    assert retained is not None
    assert retained.source_feedback_id is None


@pytest.mark.anyio
async def test_regression_run_compares_answer_safety_rule_and_error(
    db_session: Session,
) -> None:
    _child, assistant = _conversation_with_turn(db_session)
    service = QualityService(db_session)
    feedback = _feedback(service, assistant)
    case = service.create_regression_case(
        RegressionCaseWriteRequest(
            confirmed=True,
            source_feedback_id=feedback.id,
            agent_id="teacher_friend",
            title="Safety transform",
            prompt="Проверка",
            expected_response="Безопасный ответ",
            expected_safety_status="guardrail",
            expected_safety_rule_id="input.example.transform",
            expected_technical_error="none",
        )
    )
    studio = AsyncMock()
    studio.test_agent.return_value = AgentTestResponse(
        raw_response="Сырой ответ",
        final_response="  Безопасный   ответ ",
        safety_status="guardrail",
        safety_rule_id="input.example.transform",
        safety_reason="test",
        llm_duration_ms=42,
    )

    result = await service.run_regression_case(case.id, studio)

    assert result.comparison.overall_matches is True
    assert result.actual_technical_error == "none"
    assert result.llm_duration_ms == 42


@pytest.mark.anyio
async def test_quality_api_is_protected_and_exports_only_confirmed_cases(
    db_session: Session,
) -> None:
    _child, assistant = _conversation_with_turn(db_session)
    service = QualityService(db_session)
    feedback = _feedback(service, assistant)
    service.create_regression_case(
        RegressionCaseWriteRequest(
            confirmed=True,
            source_feedback_id=feedback.id,
            agent_id="teacher_friend",
            title="Confirmed case",
            prompt="Обезличенный вопрос",
            expected_response="Обезличенный ответ",
            expected_safety_status="passed",
            expected_technical_error="none",
        )
    )
    admin_app.dependency_overrides[get_quality_service] = lambda: service
    admin_app.dependency_overrides[get_studio_service] = lambda: SimpleNamespace()
    transport = ASGITransport(app=admin_app)
    try:
        async with AsyncClient(transport=transport, base_url="http://admin") as client:
            unauthorized = await client.get("/api/quality/summary")
            admin_app.dependency_overrides[_verify_admin] = lambda: "admin"
            exported = await client.get("/api/quality/regression-cases-export")
    finally:
        admin_app.dependency_overrides.clear()

    assert unauthorized.status_code == 401
    assert exported.status_code == 200
    assert "attachment" in exported.headers["content-disposition"]
    serialized = exported.text
    assert "Обезличенный вопрос" in serialized
    assert assistant.content not in serialized
