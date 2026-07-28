"""Tests for protected versioned agent administration."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from gateway.admin.agent_schemas import AgentUpdateRequest
from gateway.admin.agents_router import get_agent_admin_session
from gateway.admin.auth import verify_admin
from gateway.admin.main import app as admin_app
from gateway.app.agents import SqlAlchemyAgentRepository
from gateway.app.models import Agent, AgentRevision
from gateway.app.services.agent_service import AgentService


def test_agent_update_accepts_visual_search_capability() -> None:
    payload = AgentUpdateRequest(
        display_name="Байтик",
        description="Объясняет технологии",
        icon="🦝",
        color="navy",
        greeting="Давай разберёмся вместе!",
        tts_voice="fahad",
        tools=["web_search", "image_search"],
        permissions=[],
        enabled=True,
        sort_order=70,
    )

    assert payload.tools == ["web_search", "image_search"]


@pytest.fixture
def authenticated_admin(db_session: Session):
    admin_app.dependency_overrides[verify_admin] = lambda: "admin"
    admin_app.dependency_overrides[get_agent_admin_session] = lambda: db_session
    try:
        yield
    finally:
        admin_app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_agent_admin_api_requires_authentication() -> None:
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://admin") as client:
        response = await client.get("/api/agents")

    assert response.status_code == 401


@pytest.mark.anyio
async def test_admin_can_view_safety_baseline_and_prompt_versions(
    authenticated_admin,
) -> None:
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://admin") as client:
        response = await client.get("/api/agents")

    assert response.status_code == 200
    body = response.json()
    assert "шести лет" in body["safety_baseline"]
    assert body["safety_baseline_version"] == 0
    assert len(body["items"]) == 8
    assert body["items"][0]["revisions"][0]["is_active"] is True
    assert body["items"][0]["revisions"][0]["system_prompt"]


@pytest.mark.anyio
async def test_new_prompt_revision_is_immutable_until_explicitly_published(
    authenticated_admin,
    db_session: Session,
) -> None:
    agent = db_session.get(Agent, "scientist")
    assert agent is not None
    original_revision_id = agent.active_revision_id
    transport = ASGITransport(app=admin_app)

    async with AsyncClient(transport=transport, base_url="http://admin") as client:
        created = await client.post(
            "/api/agents/scientist/revisions",
            json={
                "system_prompt": (
                    "Помогай Лере исследовать мир через безопасные опыты, "
                    "наблюдения и короткие вопросы."
                )
            },
        )
        assert created.status_code == 200
        revision_id = uuid.UUID(created.json()["id"])
        db_session.refresh(agent)
        assert agent.active_revision_id == original_revision_id

        published = await client.post(
            f"/api/agents/scientist/revisions/{revision_id}/publish"
        )

    assert published.status_code == 200
    db_session.refresh(agent)
    assert agent.active_revision_id == revision_id
    revision = db_session.get(AgentRevision, revision_id)
    assert revision is not None
    assert revision.version == 2
    assert revision.created_by == "admin"


@pytest.mark.anyio
async def test_admin_can_publish_a_new_global_safety_baseline(
    authenticated_admin,
    db_session: Session,
) -> None:
    prompt = (
        "Ты работаешь только как безопасный детский помощник Леры шести лет. "
        "Отвечай по-русски, не проси секретов и персональных данных. "
        "Опасные действия обсуждай только с обязательным участием родителей. "
        "Поддерживай отдых, движение и живое общение вне экрана."
    )
    transport = ASGITransport(app=admin_app)

    async with AsyncClient(transport=transport, base_url="http://admin") as client:
        updated = await client.put(
            "/api/agents/safety-baseline",
            json={"system_prompt": prompt},
        )
        listed = await client.get("/api/agents")

    assert updated.status_code == 200
    assert updated.json()["version"] == 1
    assert updated.json()["created_by"] == "admin"
    assert listed.status_code == 200
    assert listed.json()["safety_baseline"] == prompt
    assert listed.json()["safety_baseline_version"] == 1
    agent_service = AgentService(SqlAlchemyAgentRepository(db_session))
    assert agent_service.get_safety_baseline() == prompt
