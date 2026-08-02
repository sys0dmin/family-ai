"""Tests for the stateless protected test studio orchestration."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gateway.admin.studio_service import SAFE_FALLBACK, StudioService
from gateway.app.providers.schemas import (
    ChatResponse,
    ImageUnderstandingResponse,
    ProviderRole,
    TranscriptionResponse,
)
from gateway.app.services.safety_service import SafetyService


@pytest.mark.anyio
async def test_studio_returns_raw_and_safe_model_output() -> None:
    provider = AsyncMock()
    provider.generate_response.return_value = ChatResponse(content="Привет, Лера!")
    agents = Mock()
    agents.get_active.return_value = SimpleNamespace(
        system_prompt="Будь добрым учителем.",
        tools=(),
        permissions=(),
    )
    agents.get_safety_baseline.return_value = "Не причиняй вреда ребёнку."
    service = StudioService(provider, provider, agents, SafetyService())

    result = await service.test_agent("teacher_friend", "Расскажи интересный факт")

    assert result.raw_response == "Привет, Лера!"
    assert result.final_response == "Привет, Лера!"
    assert result.safety_status == "passed"
    assert result.llm_duration_ms is not None


@pytest.mark.anyio
async def test_studio_explains_blocked_model_output() -> None:
    provider = AsyncMock()
    provider.generate_response.return_value = ChatResponse(
        content="Пароль: secret-value"
    )
    agents = Mock()
    agents.get_active.return_value = SimpleNamespace(
        system_prompt="Будь добрым учителем.",
        tools=(),
        permissions=(),
    )
    agents.get_safety_baseline.return_value = "Не причиняй вреда ребёнку."
    service = StudioService(provider, provider, agents, SafetyService())

    result = await service.test_agent("teacher_friend", "Привет")

    assert result.raw_response == "Пароль: secret-value"
    assert result.final_response == SAFE_FALLBACK
    assert result.safety_status == "blocked"
    assert result.safety_rule_id == "output.privacy.secret.block"


@pytest.mark.anyio
async def test_studio_uses_same_confirmed_memory_context_as_production() -> None:
    provider = AsyncMock()
    provider.generate_response.return_value = ChatResponse(content="Ответ")
    agents = Mock()
    agents.get_active.return_value = SimpleNamespace(
        system_prompt="Будь добрым учителем.",
        tools=(),
        permissions=(),
    )
    agents.get_safety_baseline.return_value = "Не причиняй вреда ребёнку."
    memory = Mock()
    memory.build_prompt_context.return_value = "Подтверждённый интерес: космос"
    service = StudioService(provider, provider, agents, SafetyService(), memory)

    await service.test_agent("teacher_friend", "Расскажи интересный факт")

    request = provider.generate_response.await_args.args[0]
    assert any(
        message.role == ProviderRole.SYSTEM
        and "Подтверждённый интерес" in message.content
        for message in request.messages
    )


@pytest.mark.anyio
async def test_studio_transcription_is_stateless_provider_orchestration() -> None:
    provider = AsyncMock()
    provider.transcribe_audio.return_value = TranscriptionResponse(
        text="Проверка связи",
        confidence=0.91,
    )
    service = StudioService(
        provider,
        provider,
        Mock(),
        SafetyService(),
        recognition_provider=provider,
    )

    result = await service.transcribe(
        b"synthetic-audio",
        filename="smoke.wav",
        content_type="audio/wav",
    )

    assert result.text == "Проверка связи"
    request = provider.transcribe_audio.await_args.args[0]
    assert request.filename == "smoke.wav"


@pytest.mark.anyio
async def test_studio_vision_is_stateless_provider_orchestration() -> None:
    provider = AsyncMock()
    provider.describe_image.return_value = ImageUnderstandingResponse(
        description="Синий квадрат"
    )
    service = StudioService(
        provider,
        provider,
        Mock(),
        SafetyService(),
        image_provider=provider,
    )

    result = await service.inspect_image(
        b"synthetic-image",
        content_type="image/png",
        question="Какого цвета квадрат?",
    )

    assert result == "Синий квадрат"
