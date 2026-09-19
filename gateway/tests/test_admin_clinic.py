"""Protected pretend-clinic preview and lifecycle administration tests."""

import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from gateway.admin.auth import verify_admin
from gateway.admin.clinic_router import get_clinic_admin_session
from gateway.admin.main import app as admin_app
from gateway.app.models import ClinicSession

REPOSITORY = Path(__file__).resolve().parents[2]


@pytest.fixture
def authenticated_clinic_admin(db_session: Session):
    admin_app.dependency_overrides[verify_admin] = lambda: "admin"
    admin_app.dependency_overrides[get_clinic_admin_session] = lambda: db_session
    try:
        yield
    finally:
        admin_app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_clinic_admin_requires_authentication() -> None:
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://admin") as client:
        response = await client.get("/api/clinic/catalog")

    assert response.status_code == 401


@pytest.mark.anyio
async def test_admin_previews_pauses_resumes_and_resets_clinic_session(
    authenticated_clinic_admin,
    db_session: Session,
    client: AsyncClient,
) -> None:
    conversation = await client.post(
        "/v1/conversations/",
        json={"agent_id": "clinic_guide"},
    )
    conversation_id = conversation.json()["conversation_id"]
    started = await client.post(
        f"/v1/clinic/conversations/{conversation_id}/cases/teddy_after_walk/start"
    )
    session_id = started.json()["session"]["id"]
    transport = ASGITransport(app=admin_app)

    async with AsyncClient(transport=transport, base_url="http://admin") as admin:
        catalog = await admin.get("/api/clinic/catalog")
        sessions = await admin.get("/api/clinic/sessions")
        paused = await admin.post(f"/api/clinic/sessions/{session_id}/pause")
        resumed = await admin.post(f"/api/clinic/sessions/{session_id}/resume")
        reset = await admin.delete(f"/api/clinic/sessions/{session_id}")

    assert catalog.status_code == 200
    assert catalog.json()["schema_version"] == 2
    assert len(catalog.json()["items"]) == 6
    assert catalog.json()["items"][0]["vitals"]
    assert catalog.json()["items"][0]["actions"]
    assert sessions.status_code == 200
    assert sessions.json()["items"][0]["case_id"] == "teddy_after_walk"
    assert paused.json()["status"] == "paused"
    assert resumed.json()["status"] == "active"
    assert reset.status_code == 204
    assert db_session.get(ClinicSession, uuid.UUID(session_id)) is None


def test_admin_panel_loads_clinic_studio_module() -> None:
    panel = (REPOSITORY / "gateway/admin/panel.html").read_text(encoding="utf-8")
    app = (REPOSITORY / "gateway/admin/static/js/app.js").read_text(encoding="utf-8")

    assert 'id="clinic-preview-select"' in panel
    assert 'id="clinic-session-list"' in panel
    assert 'from "./clinic-screen.js?v=admin-modules-4"' in app
    assert "clinicScreen.load();" in app


@pytest.mark.anyio
async def test_admin_can_version_and_publish_clinic_draft(
    authenticated_clinic_admin,
) -> None:
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://admin") as admin:
        created = await admin.post(
            "/api/clinic/drafts",
            json={
                "case_id": "teddy_after_walk",
                "payload": {"mood": "радостное", "complaint": "Хочет отдохнуть."},
            },
        )
        listed = await admin.get("/api/clinic/drafts")
        published = await admin.post(f"/api/clinic/drafts/{created.json()['id']}/publish")
        catalog = await admin.get("/api/clinic/catalog")

    assert created.status_code == 201
    assert created.json()["version"] == 1
    assert listed.json()[0]["status"] == "draft"
    assert published.json()["status"] == "published"
    assert catalog.json()["items"][0]["mood"] == "радостное"


@pytest.mark.anyio
async def test_admin_can_create_and_publish_a_new_patient_from_safe_template(
    authenticated_clinic_admin,
) -> None:
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://admin") as admin:
        created = await admin.post(
            "/api/clinic/custom-patients",
            json={
                "template_case_id": "teddy_after_walk",
                "payload": {
                    "patient_name": "Котёнок Пушок",
                    "patient_icon": "🐱",
                    "mood": "любопытное",
                    "complaint": "Устал после игры в саду.",
                },
            },
        )
        assert created.status_code == 201
        draft = created.json()
        assert draft["payload"]["kind"] == "custom_case"
        assert draft["payload"]["case"]["patient_name"] == "Котёнок Пушок"
        assert draft["payload"]["case"]["actions"]

        published = await admin.post(f"/api/clinic/drafts/{draft['id']}/publish")
        catalog = await admin.get("/api/clinic/catalog")
        edited = await admin.post(
            "/api/clinic/drafts",
            json={
                "case_id": draft["case_id"],
                "payload": {"mood": "довольное"},
            },
        )
        republished = await admin.post(f"/api/clinic/drafts/{edited.json()['id']}/publish")
        updated_catalog = await admin.get("/api/clinic/catalog")

    assert published.status_code == 200
    custom = next(item for item in catalog.json()["items"] if item["id"] == draft["case_id"])
    assert custom["patient_name"] == "Котёнок Пушок"
    assert custom["actions"]
    assert republished.status_code == 200
    updated = next(
        item for item in updated_catalog.json()["items"] if item["id"] == draft["case_id"]
    )
    assert updated["mood"] == "довольное"
