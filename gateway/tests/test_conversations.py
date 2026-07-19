"""Tests for conversation message endpoints."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from gateway.app.models import Agent, Conversation, Message, MessageRole, TopicStatistic
from gateway.app.services.retention_service import RetentionService


@pytest.mark.anyio
async def test_create_message_creates_conversation_and_stores_child_line(
    client: AsyncClient,
) -> None:
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


@pytest.mark.anyio
async def test_latest_conversation_is_resumed_separately_for_each_agent(
    client: AsyncClient,
) -> None:
    scientist = await client.post(
        "/v1/conversations/",
        json={"agent_id": "scientist"},
    )
    scientist_id = scientist.json()["conversation_id"]
    await client.post(
        f"/v1/conversations/{scientist_id}/messages",
        json={"role": "child", "content": "Почему идёт дождь?"},
    )
    await client.post(
        f"/v1/conversations/{scientist_id}/messages",
        json={"role": "assistant", "content": "Облака собирают капельки воды."},
    )

    teacher = await client.post(
        "/v1/conversations/",
        json={"agent_id": "teacher_friend"},
    )
    teacher_id = teacher.json()["conversation_id"]
    await client.post(
        f"/v1/conversations/{teacher_id}/messages",
        json={"role": "child", "content": "Давай загадку"},
    )

    response = await client.get("/v1/conversations/latest?agent_id=scientist")

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == scientist_id
    assert body["agent_id"] == "scientist"
    assert [message["content"] for message in body["messages"]] == [
        "Почему идёт дождь?",
        "Облака собирают капельки воды.",
    ]
    assert body["history_truncated"] is False


@pytest.mark.anyio
async def test_explicit_empty_conversation_becomes_agent_resume_point(
    client: AsyncClient,
    db_session: Session,
) -> None:
    previous = await client.post(
        "/v1/conversations/",
        json={"agent_id": "scientist"},
    )
    await client.post(
        f"/v1/conversations/{previous.json()['conversation_id']}/messages",
        json={"role": "child", "content": "Старый разговор"},
    )
    previous_id = uuid.UUID(previous.json()["conversation_id"])
    previous_conversation = db_session.get(Conversation, previous_id)
    assert previous_conversation is not None
    previous_conversation.created_at = datetime.now(UTC) - timedelta(minutes=5)
    previous_message = db_session.scalar(
        select(Message).where(Message.conversation_id == previous_id)
    )
    assert previous_message is not None
    previous_message.created_at = datetime.now(UTC) - timedelta(minutes=5)
    db_session.commit()
    fresh = await client.post(
        "/v1/conversations/",
        json={"agent_id": "scientist"},
    )

    response = await client.get("/v1/conversations/latest?agent_id=scientist")

    assert response.status_code == 200
    assert response.json()["conversation_id"] == fresh.json()["conversation_id"]
    assert response.json()["messages"] == []


@pytest.mark.anyio
async def test_latest_conversation_ignores_expired_history(
    client: AsyncClient,
    db_session: Session,
) -> None:
    created = await client.post(
        "/v1/conversations/",
        json={"agent_id": "scientist"},
    )
    conversation_id = uuid.UUID(created.json()["conversation_id"])
    await client.post(
        f"/v1/conversations/{conversation_id}/messages",
        json={"role": "child", "content": "Очень старый разговор"},
    )
    expired_at = datetime.now(UTC) - timedelta(days=11)
    conversation = db_session.get(Conversation, conversation_id)
    assert conversation is not None
    conversation.created_at = expired_at
    conversation.started_at = expired_at
    message = db_session.scalar(
        select(Message).where(Message.conversation_id == conversation_id)
    )
    assert message is not None
    message.created_at = expired_at
    db_session.commit()

    response = await client.get("/v1/conversations/latest?agent_id=scientist")

    assert response.status_code == 200
    assert response.json()["conversation_id"] is None
    assert response.json()["messages"] == []


@pytest.mark.anyio
async def test_latest_conversation_rejects_unavailable_agent(
    client: AsyncClient,
    db_session: Session,
) -> None:
    agent = db_session.get(Agent, "scientist")
    assert agent is not None
    agent.enabled = False
    db_session.commit()

    response = await client.get("/v1/conversations/latest?agent_id=scientist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Agent is unavailable"}


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
