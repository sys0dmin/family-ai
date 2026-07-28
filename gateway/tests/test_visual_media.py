"""Tests for licensed visual attachments."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from gateway.app.dependencies import get_chat_provider, get_image_search_provider
from gateway.app.images.openverse import OpenverseImageSearchProvider
from gateway.app.images.schemas import ImageSearchResult
from gateway.app.providers.schemas import ChatResponse
from gateway.app.services.visual_media_service import OUTDOOR_IDENTIFICATION_PATTERN


@pytest.mark.anyio
async def test_tech_question_returns_visual_attachment(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    ai_provider = AsyncMock()
    ai_provider.generate_response.return_value = ChatResponse(
        content="Сервер — это компьютер, который помогает другим компьютерам."
    )
    image_provider = AsyncMock()
    image_provider.search.return_value = ImageSearchResult(
        remote_url="https://api.openverse.org/v1/images/test/thumb/",
        source_url="https://example.org/server-photo",
        title="Server rack",
        creator="Test Author",
        license_name="CC BY",
        license_url="https://creativecommons.org/licenses/by/4.0/",
    )
    app.dependency_overrides[get_chat_provider] = lambda: ai_provider
    app.dependency_overrides[get_image_search_provider] = lambda: image_provider

    conversation = await client.post(
        "/v1/conversations/",
        json={"agent_id": "tech_guide"},
    )
    conversation_id = conversation.json()["conversation_id"]
    response = await client.post(
        f"/v1/conversations/{conversation_id}/turn",
        json={"role": "child", "content": "Байтик, что такое сервер?"},
    )

    assert response.status_code == 200
    media = response.json()["media"]
    assert len(media) == 1
    assert media[0]["media_type"] == "image"
    assert media[0]["attribution"] == "Test Author · CC BY"
    assert media[0]["content_url"].startswith("/v1/media/")
    image_provider.search.assert_awaited_once_with("computer server rack")

    stored = await client.get(
        f"/v1/conversations/{conversation_id}/messages/{response.json()['id']}"
    )
    assert stored.status_code == 200
    assert stored.json()["media"][0]["title"] == "Server rack"


def test_openverse_rejects_sensitive_or_untrusted_results() -> None:
    base = {
        "thumbnail": "https://api.openverse.org/v1/images/test/thumb/",
        "foreign_landing_url": "https://example.org/photo",
        "title": "Photo",
        "creator": "Author",
        "license": "by",
        "mature": False,
        "sensitivity": [],
    }

    assert OpenverseImageSearchProvider._normalize(base) is not None
    assert OpenverseImageSearchProvider._normalize({**base, "mature": True}) is None
    assert OpenverseImageSearchProvider._normalize({**base, "sensitivity": ["mature"]}) is None
    assert OpenverseImageSearchProvider._normalize(
        {**base, "thumbnail": "https://attacker.example/image.jpg"}
    ) is None


def test_outdoor_identification_requests_do_not_qualify_for_visuals() -> None:
    assert OUTDOOR_IDENTIFICATION_PATTERN.search("Покажи, что за гриб я нашла")
    assert OUTDOOR_IDENTIFICATION_PATTERN.search("Покажи, можно ли есть эту ягоду")
    assert not OUTDOOR_IDENTIFICATION_PATTERN.search("Покажи, как выглядит лиса")
