"""Protected activity preview and lifecycle administration tests."""

import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from gateway.admin.activity_router import get_activity_admin_session
from gateway.admin.auth import verify_admin
from gateway.admin.main import app as admin_app
from gateway.app.models import ActivitySession

REPOSITORY = Path(__file__).resolve().parents[2]


@pytest.fixture
def authenticated_activity_admin(db_session: Session):
    admin_app.dependency_overrides[verify_admin] = lambda: "admin"
    admin_app.dependency_overrides[get_activity_admin_session] = lambda: db_session
    try:
        yield
    finally:
        admin_app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_activity_admin_requires_authentication() -> None:
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://admin") as client:
        response = await client.get("/api/activities/catalog")

    assert response.status_code == 401


@pytest.mark.anyio
async def test_admin_previews_catalog_and_resets_session(
    authenticated_activity_admin,
    db_session: Session,
    client: AsyncClient,
) -> None:
    conversation = await client.post(
        "/v1/conversations/",
        json={"agent_id": "tech_guide"},
    )
    conversation_id = conversation.json()["conversation_id"]
    started = await client.post(
        f"/v1/activities/conversations/{conversation_id}/build_computer/start"
    )
    session_id = started.json()["session"]["id"]
    transport = ASGITransport(app=admin_app)

    async with AsyncClient(transport=transport, base_url="http://admin") as admin:
        catalog = await admin.get("/api/activities/catalog")
        sessions = await admin.get("/api/activities/sessions")
        reset = await admin.delete(f"/api/activities/sessions/{session_id}")

    assert catalog.status_code == 200
    assert len(catalog.json()["items"]) == 13
    assert catalog.json()["items"][0]["steps"]
    assert any(item["total_steps"] == 6 for item in catalog.json()["items"])
    assert sessions.status_code == 200
    assert sessions.json()["items"][0]["activity_id"] == "build_computer"
    assert reset.status_code == 204
    assert db_session.get(ActivitySession, uuid.UUID(session_id)) is None


def test_admin_activity_preview_labels_pauses_and_pluralizes_steps() -> None:
    script = (REPOSITORY / "gateway/admin/static/js/activity-screen.js").read_text(encoding="utf-8")

    assert 'paused: "Пауза"' in script
    assert "function stepWord(count)" in script
    assert "${selected.total_steps} ${stepWord(selected.total_steps)}" in script
