"""Tests for ephemeral child image turns."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from gateway.app.dependencies import (
    get_chat_provider,
    get_image_understanding_provider,
)
from gateway.app.providers.schemas import (
    ChatResponse,
    ImageUnderstandingResponse,
)


@pytest.mark.anyio
async def test_space_guide_accepts_image_without_persisting_binary(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    chat = AsyncMock()
    chat.generate_response.return_value = ChatResponse(
        content="На снимке видно несколько ярких звёзд."
    )
    vision = AsyncMock()
    vision.describe_image.return_value = ImageUnderstandingResponse(
        description="Тёмное небо и несколько светлых точек; созвездие не определяется."
    )
    app.dependency_overrides[get_chat_provider] = lambda: chat
    app.dependency_overrides[get_image_understanding_provider] = lambda: vision

    created = await client.post(
        "/v1/conversations/",
        json={"agent_id": "space_guide"},
    )
    conversation_id = created.json()["conversation_id"]
    response = await client.post(
        f"/v1/vision/{conversation_id}/turn",
        data={"question": "Алиса, какое это созвездие?"},
        files={"file": ("sky.jpg", b"\xff\xd8\xfftest", "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json()["content"] == "На снимке видно несколько ярких звёзд."
    request = vision.describe_image.await_args.args[0]
    assert request.image_content == b"\xff\xd8\xfftest"
    assert request.question == "Алиса, какое это созвездие?"
    messages = chat.generate_response.await_args.args[0].messages
    assert any("созвездие не определяется" in message.content for message in messages)
    assert all(b"\xff\xd8\xfftest" not in message.content.encode() for message in messages)


@pytest.mark.anyio
async def test_agent_without_capability_cannot_send_image(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    vision = AsyncMock()
    app.dependency_overrides[get_image_understanding_provider] = lambda: vision
    created = await client.post(
        "/v1/conversations/",
        json={"agent_id": "teacher_friend"},
    )
    response = await client.post(
        f"/v1/vision/{created.json()['conversation_id']}/turn",
        data={"question": "Что здесь?"},
        files={"file": ("photo.png", b"\x89PNG\r\n\x1a\ntest", "image/png")},
    )

    assert response.status_code == 403
    vision.describe_image.assert_not_awaited()


@pytest.mark.anyio
async def test_image_turn_rejects_unsupported_media_type(
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/v1/conversations/",
        json={"agent_id": "space_guide"},
    )
    response = await client.post(
        f"/v1/vision/{created.json()['conversation_id']}/turn",
        data={"question": "Что здесь?"},
        files={"file": ("note.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 415


@pytest.mark.anyio
async def test_image_turn_rejects_payload_above_configured_limit(
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/v1/conversations/",
        json={"agent_id": "space_guide"},
    )
    response = await client.post(
        f"/v1/vision/{created.json()['conversation_id']}/turn",
        data={"question": "Что здесь?"},
        files={
            "file": (
                "large.jpg",
                b"\xff\xd8\xff" + b"x" * (10 * 1024 * 1024),
                "image/jpeg",
            )
        },
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Image is too large"}
