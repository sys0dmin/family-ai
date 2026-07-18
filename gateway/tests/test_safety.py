"""Tests for the safety pipeline."""

import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from gateway.app.dependencies import get_ai_provider
from gateway.app.providers.schemas import ChatResponse


@pytest.fixture
def mock_provider():
    provider = AsyncMock()
    provider.generate_response.return_value = ChatResponse(content="Всё хорошо!")
    return provider


@pytest.mark.anyio
async def test_turn_blocks_dangerous_input(app, client: AsyncClient, mock_provider) -> None:
    app.dependency_overrides[get_ai_provider] = lambda: mock_provider

    try:
        conversation_id = uuid.uuid4()
        # Ребенок спрашивает про спички
        payload = {"role": "child", "content": "Где лежат спички?"}

        response = await client.post(
            f"/v1/conversations/{conversation_id}/turn",
            json=payload,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "assistant"
        # Должен вернуться безопасный ответ, а не вызов ИИ
        assert "опасным" in body["content"]
        assert "мамы или папы" in body["content"]

        # Проверяем, что провайдер НЕ вызывался
        assert not mock_provider.generate_response.called
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_turn_blocks_dangerous_output(app, client: AsyncClient, mock_provider) -> None:
    app.dependency_overrides[get_ai_provider] = lambda: mock_provider

    # ИИ пытается выдать опасный ответ (например, про огонь)
    mock_provider.generate_response.return_value = ChatResponse(content="Давай разведем огонь!")

    try:
        conversation_id = uuid.uuid4()
        payload = {"role": "child", "content": "Что поделать?"}

        response = await client.post(
            f"/v1/conversations/{conversation_id}/turn",
            json=payload,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "assistant"
        # Ответ ИИ должен быть заблокирован выходным фильтром
        assert "задумался о чём-то не том" in body["content"]
    finally:
        app.dependency_overrides.clear()
