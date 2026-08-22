"""Tests for restart verification of the Speech runtime adapter."""

from unittest.mock import AsyncMock

import pytest

from gateway.app.config import Settings
from gateway.app.speech_runtime.schemas import (
    SpeechRuntimeSettings,
    SpeechRuntimeSettingsUpdate,
)
from gateway.app.speech_runtime.service import (
    SpeechRestartTimeoutError,
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
        stt_max_new_tokens=96,
        instance_id="old",
    )
    restarted = SpeechRuntimeSettings(
        stt_beam_size=5,
        stt_vad_filter=True,
        stt_max_new_tokens=128,
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
        SpeechRuntimeSettingsUpdate(
            stt_beam_size=5,
            stt_vad_filter=True,
            stt_max_new_tokens=128,
        )
    )

    assert result == restarted
    service._request.assert_awaited_once_with(
        "POST",
        json={
            "stt_beam_size": 5,
            "stt_vad_filter": True,
            "stt_max_new_tokens": 128,
        },
    )


@pytest.mark.anyio
async def test_failed_speech_restart_compensates_with_previous_values() -> None:
    service = SpeechRuntimeService(
        Settings(
            speech_base_url="http://speech:8010/v1",
            speech_restart_timeout_seconds=5,
        )
    )
    previous = SpeechRuntimeSettings(
        stt_beam_size=5,
        stt_vad_filter=True,
        stt_max_new_tokens=160,
        instance_id="old",
    )
    partially_restarted = SpeechRuntimeSettings(
        stt_beam_size=3,
        stt_vad_filter=False,
        stt_max_new_tokens=128,
        instance_id="bad",
    )
    restored = previous.model_copy(update={"instance_id": "restored"})
    service.current = AsyncMock(side_effect=[previous, partially_restarted])
    service._request = AsyncMock(return_value=previous)
    service._wait_for_settings = AsyncMock(
        side_effect=[
            SpeechRestartTimeoutError("requested values not ready"),
            restored,
        ]
    )

    with pytest.raises(SpeechRestartTimeoutError, match="previous settings were restored"):
        await service.apply_and_restart(
            SpeechRuntimeSettingsUpdate(
                stt_beam_size=3,
                stt_vad_filter=False,
                stt_max_new_tokens=128,
            )
        )

    assert service._request.await_args_list[0].kwargs["json"] == {
        "stt_beam_size": 3,
        "stt_vad_filter": False,
        "stt_max_new_tokens": 128,
    }
    assert service._request.await_args_list[1].kwargs["json"] == {
        "stt_beam_size": 5,
        "stt_vad_filter": True,
        "stt_max_new_tokens": 160,
    }
