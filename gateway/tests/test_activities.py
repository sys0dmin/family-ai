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

ORIGINAL_ACTIVITY_IDS = {
    "space_expedition",
    "murka_hike",
    "build_computer",
    "guess_animal",
    "shared_story",
}
LONG_ACTIVITY_AGENTS = {
    "star_signal": "space_guide",
    "forest_lantern_mystery": "outdoor_guide",
    "cloud_city_rescue": "tech_guide",
    "rainbow_lab_mystery": "scientist",
    "dragon_lullaby": "musician",
    "dream_city_colors": "storyteller",
    "island_of_choices": "socrates",
    "museum_of_questions": "teacher_friend",
}


def test_catalog_keeps_originals_and_adds_long_adventure_for_every_agent() -> None:
    catalog = ActivityCatalog()

    activities = catalog.list()
    by_id = {item.id: item for item in activities}

    assert catalog.schema_version == 2
    assert len(activities) == 13
    assert set(by_id) == ORIGINAL_ACTIVITY_IDS | set(LONG_ACTIVITY_AGENTS)
    assert all(len(by_id[item_id].steps) == 4 for item_id in ORIGINAL_ACTIVITY_IDS)
    for activity_id, agent_id in LONG_ACTIVITY_AGENTS.items():
        activity = by_id[activity_id]
        assert activity.agent_id == agent_id
        assert len(activity.steps) == 6
        assert activity.steps[-1].instruction.startswith("Это финальный шаг.")


@pytest.mark.anyio
async def test_agent_catalog_returns_original_before_new_adventure(client: AsyncClient) -> None:
    response = await client.get("/v1/activities", params={"agent_id": "space_guide"})

    assert response.status_code == 200
    assert response.json()["schema_version"] == 2
    assert [item["id"] for item in response.json()["items"]] == [
        "space_expedition",
        "star_signal",
    ]


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
async def test_long_adventure_finishes_only_after_six_child_choices(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    provider = AsyncMock()
    provider.generate_response.return_value = ChatResponse(content="История продолжается.")
    app.dependency_overrides[get_chat_provider] = lambda: provider
    conversation = await client.post(
        "/v1/conversations/",
        json={"agent_id": "space_guide"},
    )
    conversation_id = conversation.json()["conversation_id"]
    started = await client.post(f"/v1/activities/conversations/{conversation_id}/star_signal/start")

    assert started.status_code == 200
    assert started.json()["session"]["total_steps"] == 6
    for index in range(5):
        response = await client.post(
            f"/v1/conversations/{conversation_id}/turn",
            json={"role": "child", "content": f"Выбор {index}"},
        )
        assert response.status_code == 200
    before_final = await client.get(f"/v1/activities/conversations/{conversation_id}")
    assert before_final.json()["session"]["status"] == "active"
    assert before_final.json()["session"]["current_step"] == 5

    final = await client.post(
        f"/v1/conversations/{conversation_id}/turn",
        json={"role": "child", "content": "Возвращаемся домой"},
    )
    finished = await client.get(f"/v1/activities/conversations/{conversation_id}")

    assert final.status_code == 200
    assert finished.json()["session"]["status"] == "completed"
    assert provider.generate_response.await_count == 6


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
