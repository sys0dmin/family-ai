"""Tests for AI-powered conversation turns."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from gateway.app.dependencies import get_chat_provider
from gateway.app.providers.openai_chat import OpenAIChatProvider
from gateway.app.providers.schemas import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ProviderRole,
    ProviderTool,
)


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
    app.dependency_overrides[get_chat_provider] = lambda: mock_provider

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


@pytest.mark.anyio
async def test_process_turn_removes_provider_nul_bytes_before_persistence(
    app: FastAPI,
    client: AsyncClient,
    mock_provider,
) -> None:
    app.dependency_overrides[get_chat_provider] = lambda: mock_provider
    mock_provider.generate_response.return_value = ChatResponse(
        content="Сказка\x00 готова.\x00",
    )

    conversation_id = uuid.uuid4()
    response = await client.post(
        f"/v1/conversations/{conversation_id}/turn",
        json={"role": "child", "content": "Расскажи сказку"},
    )

    assert response.status_code == 200
    assert response.json()["content"] == "Сказка готова."


@pytest.mark.anyio
async def test_follow_up_turn_is_marked_as_same_conversation(
    app: FastAPI,
    client: AsyncClient,
    mock_provider,
) -> None:
    app.dependency_overrides[get_chat_provider] = lambda: mock_provider
    conversation = await client.post(
        "/v1/conversations/",
        json={"agent_id": "musician"},
    )
    conversation_id = conversation.json()["conversation_id"]

    await client.post(
        f"/v1/conversations/{conversation_id}/turn",
        json={"role": "child", "content": "Угадай песню"},
    )
    await client.post(
        f"/v1/conversations/{conversation_id}/turn",
        json={"role": "child", "content": "Это Король и Шут"},
    )

    request = mock_provider.generate_response.await_args_list[-1].args[0]
    system_messages = [
        message.content for message in request.messages if message.role == ProviderRole.SYSTEM
    ]
    assert any("продолжение уже начатого разговора" in text for text in system_messages)
    assert any("коротко признай поправку" in text for text in system_messages)
    assert any("инструмент распознавания музыки не возвращал" in text for text in system_messages)
    assert request.tools == (ProviderTool.WEB_SEARCH,)


@pytest.mark.anyio
async def test_outdoor_guide_can_use_web_search_for_nature_facts(
    app: FastAPI,
    client: AsyncClient,
    mock_provider,
) -> None:
    app.dependency_overrides[get_chat_provider] = lambda: mock_provider
    conversation = await client.post(
        "/v1/conversations/",
        json={"agent_id": "outdoor_guide"},
    )

    await client.post(
        f"/v1/conversations/{conversation.json()['conversation_id']}/turn",
        json={"role": "child", "content": "Чем опасен багульник?"},
    )

    request = mock_provider.generate_response.await_args.args[0]
    assert request.tools == (ProviderTool.WEB_SEARCH,)


@pytest.mark.anyio
async def test_tech_guide_can_use_web_search_for_current_it_facts(
    app: FastAPI,
    client: AsyncClient,
    mock_provider,
) -> None:
    app.dependency_overrides[get_chat_provider] = lambda: mock_provider
    conversation = await client.post(
        "/v1/conversations/",
        json={"agent_id": "tech_guide"},
    )

    await client.post(
        f"/v1/conversations/{conversation.json()['conversation_id']}/turn",
        json={"role": "child", "content": "Что такое X5 Salt?"},
    )

    request = mock_provider.generate_response.await_args.args[0]
    assert request.tools == (ProviderTool.WEB_SEARCH,)


@pytest.mark.anyio
async def test_openai_provider_maps_generic_web_search_tool() -> None:
    provider = OpenAIChatProvider(
        api_key="test-key",
        model="openai/gpt-oss-120b",
        base_url="https://api.groq.com/openai/v1",
        web_search_tool_type="browser_search",
    )
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Найдено"))]
        )
    )
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    request_id = uuid.uuid4()
    response = await provider.generate_response(
        ChatRequest(
            messages=[ChatMessage(role=ProviderRole.USER, content="Найди песню")],
            tools=(ProviderTool.WEB_SEARCH,),
            request_id=request_id,
        )
    )

    assert response.content == "Найдено"
    create.assert_awaited_once_with(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": "Найди песню"}],
        temperature=0.7,
        max_tokens=None,
        tools=[{"type": "browser_search"}],
        extra_headers={"X-Request-ID": str(request_id)},
    )
