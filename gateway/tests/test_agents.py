"""Tests for child-safe, versioned agent selection."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from gateway.app.agents import SqlAlchemyAgentRepository
from gateway.app.models import Agent, AgentRevision, Conversation
from gateway.app.services.agent_service import AgentService
from gateway.app.services.conversation_service import ConversationService


@pytest.mark.anyio
async def test_agent_manifest_exposes_only_child_safe_metadata(
    client: AsyncClient,
) -> None:
    response = await client.get("/v1/agents")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [
        "teacher_friend",
        "scientist",
        "storyteller",
        "socrates",
        "musician",
        "outdoor_guide",
        "tech_guide",
        "space_guide",
    ]
    assert all("system_prompt" not in item for item in items)
    assert all("tts_voice" not in item for item in items)
    assert set(items[0]) == {
        "id",
        "display_name",
        "description",
        "icon",
        "color",
        "greeting",
        "supports_image_upload",
        "supports_spoken_image_question",
        "image_upload_max_bytes",
    }
    assert items[0]["image_upload_max_bytes"] == 10 * 1024 * 1024
    assert items[0]["supports_spoken_image_question"] is True
    assert items[1]["image_upload_max_bytes"] is None
    assert items[-1]["image_upload_max_bytes"] == 10 * 1024 * 1024


@pytest.mark.anyio
async def test_child_interface_serves_visual_first_agent_assets(
    client: AsyncClient,
) -> None:
    page = await client.get("/")

    assert page.status_code == 200
    assert "Клуб любопытных" in page.text
    assert 'id="mic-btn"' in page.text
    assert "browser-speech-toggle" in page.text
    assert 'id="activity-open"' in page.text
    assert 'id="activity-dialog"' in page.text
    assert 'src="/static/app.js?v=18"' in page.text
    assert page.text.count('class="icon-button new-conversation"') == 2
    assert 'data-state="ready"' in page.text

    for filename in (
        "teacher-friend.webp",
        "scientist.webp",
        "storyteller.webp",
        "socrates.webp",
        "musician.webp",
        "murka.webp",
        "baytik.webp",
        "alice-selezneva.webp",
    ):
        asset = await client.get(f"/static/assets/characters/{filename}")
        assert asset.status_code == 200
        assert asset.headers["content-type"] == "image/webp"
        assert len(asset.content) > 10_000


@pytest.mark.anyio
async def test_selected_agent_and_revision_are_bound_to_new_conversation(
    client: AsyncClient,
    db_session: Session,
) -> None:
    response = await client.post(
        "/v1/conversations/",
        json={"agent_id": "scientist"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["agent_id"] == "scientist"
    conversation = db_session.get(Conversation, uuid.UUID(body["conversation_id"]))
    assert conversation is not None
    assert conversation.agent_id == "scientist"
    assert conversation.agent_revision_id == uuid.UUID(
        "a0000000-0000-0000-0000-000000000002"
    )


@pytest.mark.anyio
async def test_unavailable_agent_cannot_start_conversation(
    client: AsyncClient,
    db_session: Session,
) -> None:
    agent = db_session.get(Agent, "scientist")
    assert agent is not None
    agent.enabled = False
    db_session.commit()

    response = await client.post(
        "/v1/conversations/",
        json={"agent_id": "scientist"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Agent is unavailable"}


def test_existing_conversation_keeps_published_revision(db_session: Session) -> None:
    agents = AgentService(SqlAlchemyAgentRepository(db_session))
    conversations = ConversationService(db_session, agents=agents)
    conversation = conversations.create_conversation("scientist")
    original_revision_id = conversation.agent_revision_id

    new_revision = AgentRevision(
        id=uuid.uuid4(),
        agent_id="scientist",
        version=2,
        system_prompt="Новая версия личности, только для новых разговоров.",
        created_by="test",
    )
    db_session.add(new_revision)
    db_session.flush()
    agent = db_session.get(Agent, "scientist")
    assert agent is not None
    agent.active_revision_id = new_revision.id
    db_session.flush()

    bound_agent = conversations.get_conversation_agent(conversation.id)

    assert bound_agent.revision_id == str(original_revision_id)
    assert bound_agent.version == 1
    assert bound_agent.system_prompt != new_revision.system_prompt
