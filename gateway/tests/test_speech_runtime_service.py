"""Tests for restart verification of the Speech runtime adapter."""

from unittest.mock import AsyncMock

import pytest

from gateway.app.config import Settings
from gateway.app.speech_runtime.schemas import (
    SpeechRuntimeSettings,
    SpeechRuntimeSettingsUpdate,
)
from gateway.app.speech_runtime.service import (
    SpeechRuntimeService,
    SpeechRuntimeUnavailableError,
)


@pytest.mark.anyio
async def test_apply_waits_for_new_process_with_requested_values(monkeypatch) -> None:
    service = SpeechRuntimeService(
        Settings(
            speech_base_url="http://speech:8010/v1",
            speech_restart_timeout_seconds=5,
        )
    )
    previous = SpeechRuntimeSettings(
        stt_beam_size=1,
        stt_vad_filter=True,
        instance_id="old",
    )
    restarted = SpeechRuntimeSettings(
        stt_beam_size=5,
        stt_vad_filter=True,
        instance_id="new",
    )
    service.current = AsyncMock(
        side_effect=[
            previous,
            SpeechRuntimeUnavailableError("restarting"),
            restarted,
        ]
    )
    service._request = AsyncMock(return_value=previous)
    monkeypatch.setattr(
        "gateway.app.speech_runtime.service.asyncio.sleep",
        AsyncMock(),
    )

    result = await service.apply_and_restart(
        SpeechRuntimeSettingsUpdate(stt_beam_size=5, stt_vad_filter=True)
    )

    assert result == restarted
    service._request.assert_awaited_once_with(
        "POST",
        json={"stt_beam_size": 5, "stt_vad_filter": True},
    )
