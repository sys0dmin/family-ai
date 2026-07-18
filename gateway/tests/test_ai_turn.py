"""Tests for AI-powered conversation turns."""

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from gateway.app.dependencies import get_ai_provider
from gateway.app.providers.schemas import ChatResponse


@pytest.fixture
def mock_provider():
    """Create a mock AI provider."""
    provider = AsyncMock()
    provider.generate_response.return_value = ChatResponse(
        content="Это тестовый ответ от ИИ. Как твои дела?"
    )
    return provider


@pytest.mark.anyio
async def test_process_turn_generates_ai_response(
    app: FastAPI,
    client: AsyncClient,
    mock_provider,
) -> None:
    # Override the dependency on the app instance provided by the fixture
    app.dependency_overrides[get_ai_provider] = lambda: mock_provider

    conversation_id = uuid.uuid4()
    payload = {"role": "child", "content": "Привет, расскажи сказку"}

    response = await client.post(
        f"/v1/conversations/{conversation_id}/turn",
        json=payload,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "assistant"
    assert body["content"] == "Это тестовый ответ от ИИ. Как твои дела?"
    assert body["conversation_id"] == str(conversation_id)

    # Verify provider was called
    assert mock_provider.generate_response.called
