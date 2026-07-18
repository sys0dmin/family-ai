"""Tests for protected versioned agent administration."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from gateway.admin.agents_router import get_agent_admin_session
from gateway.admin.auth import verify_admin
from gateway.admin.main import app as admin_app
from gateway.app.models import Agent, AgentRevision


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
    assert len(body["items"]) == 4
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
