"""Contracts for the parent-armed child-speech calibration transport."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from gateway.app.calibration.schemas import CalibrationStatusResponse
from gateway.app.dependencies import (
    get_speech_calibration_service,
    get_speech_synthesis_provider,
)
from gateway.app.providers.schemas import SpeechResponse


def calibration_state(
    *,
    status: str = "collecting",
    collected_prompt_ids: list[str] | None = None,
) -> CalibrationStatusResponse:
    now = datetime.now(UTC)
    return CalibrationStatusResponse(
        id="calibration-123",
        status=status,
        created_at=now,
        expires_at=now + timedelta(hours=24),
        prompts_total=15,
        samples_collected=len(collected_prompt_ids or []),
        collected_prompt_ids=collected_prompt_ids or [],
        current_trial=0,
        total_trials=90,
        results=[],
        recommended_beam_size=None,
        recommended_vad_filter=None,
        error=None,
    )


@pytest.mark.anyio
async def test_active_calibration_exposes_only_server_defined_prompts(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    service = AsyncMock()
    service.current.return_value = calibration_state(
        collected_prompt_ids=["speech_01"]
    )
    app.dependency_overrides[get_speech_calibration_service] = lambda: service

    response = await client.get("/v1/stt-calibration/active")

    assert response.status_code == 200
    body = response.json()
    assert body["active"] is True
    assert body["session_id"] == "calibration-123"
    assert len(body["prompts"]) == 15
    assert body["collected_prompt_ids"] == ["speech_01"]
    assert body["prompts"][0]["phrase"] == "Привет, меня зовут Лера."


@pytest.mark.anyio
async def test_prompt_audio_and_wav_upload_use_existing_abstractions(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    service = AsyncMock()
    service.current.return_value = calibration_state()
    provider = AsyncMock()
    provider.synthesize_speech.return_value = SpeechResponse(
        audio_content=b"RIFF-prompt",
        content_type="audio/wav",
    )
    app.dependency_overrides[get_speech_calibration_service] = lambda: service
    app.dependency_overrides[get_speech_synthesis_provider] = lambda: provider

    prompt_audio = await client.get(
        "/v1/stt-calibration/calibration-123/prompts/speech_01/audio"
    )
    upload = await client.post(
        "/v1/stt-calibration/calibration-123/samples/speech_01",
        files={"file": ("sample.wav", b"RIFF-child", "audio/wav")},
    )

    assert prompt_audio.status_code == 200
    assert prompt_audio.content == b"RIFF-prompt"
    assert upload.status_code == 204
    service.add_sample.assert_awaited_once_with(
        "calibration-123",
        "speech_01",
        b"RIFF-child",
        "audio/wav",
    )


@pytest.mark.anyio
async def test_calibration_is_hidden_when_benchmark_is_not_collecting(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    service = AsyncMock()
    service.current.return_value = calibration_state(status="running")
    app.dependency_overrides[get_speech_calibration_service] = lambda: service

    response = await client.get("/v1/stt-calibration/active")

    assert response.status_code == 200
    assert response.json() == {
        "active": False,
        "session_id": None,
        "prompts": [],
        "collected_prompt_ids": [],
    }
