"""Tests for the stateless protected test studio orchestration."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gateway.admin.studio_service import SAFE_FALLBACK, StudioService
from gateway.app.providers.schemas import ChatResponse
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
    service = StudioService(provider, agents, SafetyService())

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
    service = StudioService(provider, agents, SafetyService())

    result = await service.test_agent("teacher_friend", "Привет")

    assert result.raw_response == "Пароль: secret-value"
    assert result.final_response == SAFE_FALLBACK
    assert result.safety_status == "blocked"
    assert result.safety_rule_id == "output.secret_value"
