"""Configured activity lifecycle and conversation integration tests."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gateway.app.activities import ActivityCatalog
from gateway.app.dependencies import get_chat_provider
from gateway.app.models import ActivitySession, LongTermMemory
from gateway.app.providers.schemas import ChatResponse, ProviderRole


def test_catalog_contains_five_short_validated_activities() -> None:
    catalog = ActivityCatalog()

    activities = catalog.list()

    assert len(activities) == 5
    assert {item.id for item in activities} == {
        "space_expedition",
        "murka_hike",
        "build_computer",
        "guess_animal",
        "shared_story",
    }
    assert all(2 <= len(item.steps) <= 6 for item in activities)


@pytest.mark.anyio
async def test_activity_start_requires_matching_conversation_agent(
    client: AsyncClient,
) -> None:
    conversation = await client.post(
        "/v1/conversations/",
        json={"agent_id": "tech_guide"},
    )
    conversation_id = conversation.json()["conversation_id"]

    wrong = await client.post(
        f"/v1/activities/conversations/{conversation_id}/space_expedition/start"
    )
    started = await client.post(
        f"/v1/activities/conversations/{conversation_id}/build_computer/start"
    )

    assert wrong.status_code == 409
    assert started.status_code == 200
    assert started.json()["session"]["status"] == "active"
    assert started.json()["session"]["current_step"] == 0
    assert started.json()["message"]["role"] == "assistant"


@pytest.mark.anyio
async def test_activity_advances_through_normal_conversation_pipeline(
    app: FastAPI,
    client: AsyncClient,
    db_session: Session,
) -> None:
    provider = AsyncMock()
    provider.generate_response.return_value = ChatResponse(content="Шаг готов.")
    app.dependency_overrides[get_chat_provider] = lambda: provider
    conversation = await client.post(
        "/v1/conversations/",
        json={"agent_id": "tech_guide"},
    )
    conversation_id = conversation.json()["conversation_id"]
    await client.post(f"/v1/activities/conversations/{conversation_id}/build_computer/start")

    for index in range(4):
        response = await client.post(
            f"/v1/conversations/{conversation_id}/turn",
            json={"role": "child", "content": f"Мой выбор {index}"},
        )
        assert response.status_code == 200

    request = provider.generate_response.await_args_list[-1].args[0]
    system_text = "\n".join(
        message.content for message in request.messages if message.role is ProviderRole.SYSTEM
    )
    state = await client.get(f"/v1/activities/conversations/{conversation_id}")

    assert "последний шаг" in system_text.casefold()
    assert state.json()["session"]["status"] == "completed"
    assert state.json()["session"]["completion_summary"]
    assert db_session.scalar(select(func.count(LongTermMemory.id))) == 0


@pytest.mark.anyio
async def test_voice_friendly_control_intent_stops_without_calling_model(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    provider = AsyncMock()
    provider.generate_response.return_value = ChatResponse(content="Не должно прийти")
    app.dependency_overrides[get_chat_provider] = lambda: provider
    conversation = await client.post(
        "/v1/conversations/",
        json={"agent_id": "outdoor_guide"},
    )
    conversation_id = conversation.json()["conversation_id"]
    await client.post(f"/v1/activities/conversations/{conversation_id}/murka_hike/start")

    stopped = await client.post(
        f"/v1/conversations/{conversation_id}/turn",
        json={"role": "child", "content": "Давай просто поговорим!"},
    )
    state = await client.get(f"/v1/activities/conversations/{conversation_id}")

    assert stopped.status_code == 200
    assert "просто поговорить" in stopped.json()["content"]
    assert state.json()["session"]["status"] == "left"
    provider.generate_response.assert_not_awaited()


@pytest.mark.anyio
async def test_starting_another_activity_reuses_single_conversation_state(
    client: AsyncClient,
    db_session: Session,
) -> None:
    conversation = await client.post(
        "/v1/conversations/",
        json={"agent_id": "storyteller"},
    )
    conversation_id = conversation.json()["conversation_id"]

    first = await client.post(f"/v1/activities/conversations/{conversation_id}/shared_story/start")
    second = await client.post(f"/v1/activities/conversations/{conversation_id}/shared_story/start")

    assert first.json()["session"]["id"] == second.json()["session"]["id"]
    assert db_session.scalar(select(func.count(ActivitySession.id))) == 1


@pytest.mark.anyio
async def test_paused_activity_resumes_same_step_and_session(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    provider = AsyncMock()
    provider.generate_response.return_value = ChatResponse(content="Первый шаг готов.")
    app.dependency_overrides[get_chat_provider] = lambda: provider
    conversation = await client.post(
        "/v1/conversations/",
        json={"agent_id": "space_guide"},
    )
    conversation_id = conversation.json()["conversation_id"]
    started = await client.post(
        f"/v1/activities/conversations/{conversation_id}/space_expedition/start"
    )
    await client.post(
        f"/v1/conversations/{conversation_id}/turn",
        json={"role": "child", "content": "Летим на Марс"},
    )

    paused = await client.post(
        f"/v1/activities/conversations/{conversation_id}/stop",
        json={"leave_for_conversation": False},
    )
    resumed = await client.post(
        f"/v1/activities/conversations/{conversation_id}/resume",
    )

    assert paused.status_code == 200
    assert paused.json()["session"]["status"] == "paused"
    assert paused.json()["session"]["current_step"] == 1
    assert paused.json()["session"]["current_step_title"]
    assert resumed.status_code == 200
    assert resumed.json()["session"]["status"] == "active"
    assert resumed.json()["session"]["id"] == started.json()["session"]["id"]
    assert resumed.json()["session"]["current_step"] == 1
    assert "Продолжаем" in resumed.json()["message"]["content"]


@pytest.mark.anyio
async def test_resume_rejects_non_paused_activity(client: AsyncClient) -> None:
    conversation = await client.post(
        "/v1/conversations/",
        json={"agent_id": "space_guide"},
    )
    conversation_id = conversation.json()["conversation_id"]
    await client.post(f"/v1/activities/conversations/{conversation_id}/space_expedition/start")

    response = await client.post(f"/v1/activities/conversations/{conversation_id}/resume")

    assert response.status_code == 409
