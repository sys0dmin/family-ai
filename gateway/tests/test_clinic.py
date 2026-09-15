"""Deterministic pretend-clinic behavior and child API."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from gateway.app.agents import SqlAlchemyAgentRepository
from gateway.app.clinic import ClinicGameService
from gateway.app.clinic.metrics import clinic_metrics_registry
from gateway.app.models import ClinicSession
from gateway.app.services.agent_service import AgentService
from gateway.app.services.conversation_service import ConversationService


@pytest.mark.anyio
async def test_clinic_catalog_is_child_safe_and_versioned(client: AsyncClient) -> None:
    response = await client.get("/v1/clinic/cases")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == 2
    assert [item["id"] for item in body["items"]] == [
        "teddy_after_walk",
        "robot_checkup",
        "fox_after_procedure",
    ]
    assert "opening_text" not in body["items"][0]


@pytest.mark.anyio
async def test_clinic_session_actions_are_idempotent_and_complete(
    client: AsyncClient,
    db_session: Session,
) -> None:
    conversation = await client.post(
        "/v1/conversations/",
        json={"agent_id": "clinic_guide"},
    )
    conversation_id = conversation.json()["conversation_id"]

    started = await client.post(
        f"/v1/clinic/conversations/{conversation_id}/cases/teddy_after_walk/start"
    )
    assert started.status_code == 200
    assert started.json()["session"]["is_pretend"] is True
    assert started.json()["session"]["status"] == "active"

    first = await client.post(f"/v1/clinic/conversations/{conversation_id}/actions/listen_heart")
    repeated = await client.post(f"/v1/clinic/conversations/{conversation_id}/actions/listen_heart")
    assert first.status_code == repeated.status_code == 200
    assert first.json()["repeated"] is False
    assert repeated.json()["repeated"] is True

    for action_id in ("give_water", "feed", "rest"):
        response = await client.post(
            f"/v1/clinic/conversations/{conversation_id}/actions/{action_id}"
        )
        assert response.status_code == 200

    state = (
        db_session.query(ClinicSession).filter_by(conversation_id=uuid.UUID(conversation_id)).one()
    )
    db_session.refresh(state)
    assert state.status == "completed"
    assert len(state.procedure_events) == 4


@pytest.mark.anyio
async def test_clinic_cannot_start_for_another_agent(client: AsyncClient) -> None:
    conversation = await client.post(
        "/v1/conversations/",
        json={"agent_id": "teacher_friend"},
    )
    conversation_id = conversation.json()["conversation_id"]

    response = await client.post(
        f"/v1/clinic/conversations/{conversation_id}/cases/teddy_after_walk/start"
    )

    assert response.status_code == 409


@pytest.mark.parametrize(
    "complaint",
    [
        "У меня болит живот",
        "Мне плохо и кружится голова",
        "Меня тошнит",
        "Я порезалась",
        "Я проглотила таблетку",
    ],
)
def test_real_health_complaint_pauses_game_and_skips_generation(
    db_session: Session,
    complaint: str,
) -> None:
    conversations = ConversationService(
        db_session,
        agents=AgentService(SqlAlchemyAgentRepository(db_session)),
    )
    conversation = conversations.create_conversation("clinic_guide")
    clinic = ClinicGameService(db_session)
    clinic.start(conversation.id, "robot_checkup")

    response = clinic.handle_real_health_input(
        conversation.id,
        complaint,
    )

    assert response is not None
    assert "позови" in response
    assert clinic.get(conversation.id).status == "paused"


def test_clinic_prompt_exposes_only_catalog_actions(db_session: Session) -> None:
    conversations = ConversationService(
        db_session,
        agents=AgentService(SqlAlchemyAgentRepository(db_session)),
    )
    conversation = conversations.create_conversation("clinic_guide")
    clinic = ClinicGameService(db_session)
    clinic.start(conversation.id, "fox_after_procedure")

    context = clinic.turn_context(conversation.id)

    assert context is not None
    assert "Укол сделан" in context.prompt_context
    assert "не назначай" in context.prompt_context.lower()
    assert "дозу" in context.prompt_context.lower()


def test_clinic_intake_chooses_and_persists_a_plausible_vital_set(
    db_session: Session,
) -> None:
    conversations = ConversationService(
        db_session,
        agents=AgentService(SqlAlchemyAgentRepository(db_session)),
    )
    conversation = conversations.create_conversation("clinic_guide")
    clinic = ClinicGameService(
        db_session,
        vital_reading_picker=lambda readings: readings[-1],
    )

    session = clinic.start(conversation.id, "teddy_after_walk")

    assert session.vital_snapshot["pulse"]["value"] == "104"
    assert session.vital_snapshot["pressure"]["value"] == "100/65"
    assert session.vital_snapshot["temperature"]["value"] == "36,7"
    assert session.vital_snapshot["breathing"]["value"] == "24"
    assert clinic.get(conversation.id).vital_snapshot == session.vital_snapshot

    clinic.perform_action(conversation.id, "give_water")
    after_water = clinic.get(conversation.id)
    assert after_water is not None
    assert after_water.vital_snapshot["pulse"]["value"] == "92"
    assert after_water.vital_snapshot["breathing"]["value"] == "21"


def test_clinic_catalog_upgrade_closes_an_incompatible_old_appointment(
    db_session: Session,
) -> None:
    conversations = ConversationService(
        db_session,
        agents=AgentService(SqlAlchemyAgentRepository(db_session)),
    )
    conversation = conversations.create_conversation("clinic_guide")
    clinic = ClinicGameService(db_session)
    started = clinic.start(conversation.id, "teddy_after_walk")
    started.case_version = 1
    started.vital_snapshot = {"heart": {"value": "тук-тук"}}
    db_session.flush()

    restored = clinic.get(conversation.id)

    assert restored is not None
    assert restored.status == "left"
    assert restored.case_version == 2
    assert set(restored.vital_snapshot) == {"pulse", "pressure", "temperature", "breathing"}


@pytest.mark.anyio
async def test_clinic_metrics_contain_only_operation_outcomes(client: AsyncClient) -> None:
    clinic_metrics_registry.reset()
    conversation = await client.post(
        "/v1/conversations/", json={"agent_id": "clinic_guide"}
    )
    conversation_id = conversation.json()["conversation_id"]
    await client.post(
        f"/v1/clinic/conversations/{conversation_id}/cases/teddy_after_walk/start"
    )
    await client.post(
        f"/v1/clinic/conversations/{conversation_id}/actions/not_available"
    )

    response = await client.get("/internal/clinic-metrics")

    assert response.status_code == 200
    assert response.json()["counts"] == {"action.error": 1, "start.success": 1}
    assert "conversation" not in response.text
