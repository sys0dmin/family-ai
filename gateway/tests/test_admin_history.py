"""Tests for protected history dashboard read models."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from gateway.admin.history_service import HistoryService
from gateway.admin.main import (
    _verify_admin,
    get_history_service,
)
from gateway.admin.main import (
    app as admin_app,
)
from gateway.app.constants import LERA_PROFILE_ID
from gateway.app.models import Conversation, Message, MessageRole

TEACHER_REVISION_ID = uuid.UUID("a0000000-0000-0000-0000-000000000001")


def _add_message(
    session: Session,
    *,
    conversation_id: uuid.UUID,
    role: MessageRole,
    content: str,
    created_at: datetime,
) -> None:
    session.add(
        Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            role=role,
            content=content,
            created_at=created_at,
        )
    )


def test_history_summary_calculates_activity_and_questions(db_session: Session) -> None:
    now = datetime.now(UTC)
    conversation_id = uuid.uuid4()
    db_session.add(
        Conversation(
            id=conversation_id,
            child_profile_id=LERA_PROFILE_ID,
            agent_id="teacher_friend",
            agent_revision_id=TEACHER_REVISION_ID,
            started_at=now - timedelta(minutes=5),
        )
    )
    _add_message(
        db_session,
        conversation_id=conversation_id,
        role=MessageRole.CHILD,
        content="Почему небо голубое?",
        created_at=now - timedelta(seconds=8),
    )
    _add_message(
        db_session,
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content="Потому что солнечный свет рассеивается в воздухе.",
        created_at=now - timedelta(seconds=5),
    )
    _add_message(
        db_session,
        conversation_id=conversation_id,
        role=MessageRole.CHILD,
        content="Почему небо голубое?",
        created_at=now - timedelta(seconds=4),
    )
    _add_message(
        db_session,
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content="Синий свет сильнее рассеивается.",
        created_at=now - timedelta(seconds=2),
    )
    db_session.flush()

    summary = HistoryService(db_session).get_summary(days=10, now=now)

    assert summary.total_messages == 4
    assert summary.child_messages == 2
    assert summary.assistant_messages == 2
    assert summary.conversations == 1
    assert summary.active_days == 1
    assert summary.average_response_seconds == 2.5
    assert summary.frequent_questions[0].text == "Почему небо голубое?"
    assert summary.frequent_questions[0].count == 2
    assert summary.daily_activity[-1].child_messages == 2


def test_history_conversations_support_search_and_pagination(db_session: Session) -> None:
    now = datetime.now(UTC)
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    for conversation_id in (first_id, second_id):
        db_session.add(
            Conversation(
                id=conversation_id,
                child_profile_id=LERA_PROFILE_ID,
                agent_id="teacher_friend",
                agent_revision_id=TEACHER_REVISION_ID,
                started_at=now - timedelta(minutes=10),
            )
        )

    _add_message(
        db_session,
        conversation_id=first_id,
        role=MessageRole.CHILD,
        content="Расскажи про космос",
        created_at=now - timedelta(minutes=3),
    )
    _add_message(
        db_session,
        conversation_id=first_id,
        role=MessageRole.ASSISTANT,
        content="Космос очень большой.",
        created_at=now - timedelta(minutes=2),
    )
    _add_message(
        db_session,
        conversation_id=second_id,
        role=MessageRole.CHILD,
        content="Давай поговорим про динозавров",
        created_at=now - timedelta(minutes=1),
    )
    db_session.flush()

    service = HistoryService(db_session)
    all_conversations = service.get_conversations(
        days=10,
        page=1,
        page_size=1,
        now=now,
    )
    search_result = service.get_conversations(
        days=10,
        page=1,
        page_size=10,
        search="космос",
        now=now,
    )

    assert all_conversations.total == 2
    assert all_conversations.total_pages == 2
    assert len(all_conversations.items) == 1
    assert search_result.total == 1
    assert search_result.items[0].conversation_id == first_id
    assert search_result.items[0].message_count == 2
    assert len(search_result.items[0].messages) == 2


@pytest.mark.anyio
async def test_history_api_requires_admin_authentication() -> None:
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://admin") as client:
        response = await client.get("/api/history/summary")

    assert response.status_code == 401


@pytest.mark.anyio
async def test_history_api_returns_read_only_summary(db_session: Session) -> None:
    admin_app.dependency_overrides[_verify_admin] = lambda: "admin"
    admin_app.dependency_overrides[get_history_service] = lambda: HistoryService(db_session)
    try:
        transport = ASGITransport(app=admin_app)
        async with AsyncClient(transport=transport, base_url="http://admin") as client:
            response = await client.get("/api/history/summary?days=10")
    finally:
        admin_app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["days"] == 10
    assert response.json()["total_messages"] == 0
