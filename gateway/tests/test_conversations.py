"""Tests for conversation message endpoints."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from gateway.app.models import Message, MessageRole, TopicStatistic
from gateway.app.services.retention_service import RetentionService


@pytest.mark.anyio
async def test_create_message_creates_conversation_and_stores_child_line(client: AsyncClient) -> None:
    conversation_id = uuid.uuid4()

    response = await client.post(
        f"/v1/conversations/{conversation_id}/messages",
        json={"role": "child", "content": "Почему небо голубое?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == str(conversation_id)
    assert body["role"] == "child"
    assert body["content"] == "Почему небо голубое?"
    assert "created_at" in body


@pytest.mark.anyio
async def test_create_message_appends_to_existing_conversation(client: AsyncClient) -> None:
    conversation_id = uuid.uuid4()

    first = await client.post(
        f"/v1/conversations/{conversation_id}/messages",
        json={"role": "child", "content": "Привет"},
    )
    second = await client.post(
        f"/v1/conversations/{conversation_id}/messages",
        json={"role": "assistant", "content": "Привет, Лера!"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["conversation_id"] == second.json()["conversation_id"]


def test_retention_service_deletes_only_expired_messages(db_session: Session) -> None:
    conversation_id = uuid.uuid4()
    db_session.add(
        Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            role=MessageRole.CHILD,
            content="старое сообщение",
            created_at=datetime.now(UTC) - timedelta(days=11),
        )
    )
    db_session.add(
        Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content="свежее сообщение",
            created_at=datetime.now(UTC) - timedelta(days=1),
        )
    )
    db_session.flush()

    deleted = RetentionService(db_session, retention_days=10).purge_expired_messages()
    remaining = list(db_session.scalars(select(Message)))

    assert deleted == 1
    assert len(remaining) == 1
    assert remaining[0].content == "свежее сообщение"


def test_topic_statistics_do_not_store_message_text(db_session: Session) -> None:
    statistic = TopicStatistic(
        id=uuid.uuid4(),
        child_profile_id=uuid.UUID("6f3f8f2a-9c4d-4f1e-b8a2-7d1c5e9a0b12"),
        topic="космос",
        mention_count=2,
        stat_date=datetime.now(UTC).date(),
    )
    db_session.add(statistic)
    db_session.flush()

    stored = db_session.get(TopicStatistic, statistic.id)
    assert stored is not None
    assert stored.topic == "космос"
    assert "content" not in stored.__dict__
