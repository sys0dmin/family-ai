"""HTTP and timeout tests for bounded Voice execution."""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from gateway.app.config import Settings, get_settings
from gateway.app.dependencies import get_voice_service
from gateway.app.providers.schemas import SpeechResponse, TranscriptionResponse
from gateway.app.services.voice_execution import (
    VoiceExecutionPolicy,
    VoiceStageTimeoutError,
    voice_admission_controller,
    voice_timeout_message,
)
from gateway.app.services.voice_service import VoiceService


def test_stt_timeout_message_asks_to_repeat_instead_of_blame_answer() -> None:
    assert voice_timeout_message("stt") == (
        "Я не успела тебя расслышать. Скажи, пожалуйста, ещё раз покороче."
    )
    assert "Ответ не успел" in voice_timeout_message("llm")


async def _wait_for_calls(mock: AsyncMock, count: int) -> None:
    for _ in range(100):
        if mock.await_count >= count:
            return
        await asyncio.sleep(0.001)
    raise AssertionError(f"Expected {count} calls, got {mock.await_count}")


@pytest.mark.anyio
async def test_third_voice_turn_is_rejected_without_provider_work(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    voice_admission_controller.reset()
    release = asyncio.Event()
    service = AsyncMock()

    async def process(**_kwargs):
        await release.wait()
        return SimpleNamespace(
            speech=SimpleNamespace(audio_content=b"wav", content_type="audio/wav"),
            message_id=uuid.uuid4(),
        )

    service.process_voice_turn.side_effect = process
    app.dependency_overrides[get_voice_service] = lambda: service
    app.dependency_overrides[get_settings] = lambda: Settings(voice_max_in_flight=2)
    first = asyncio.create_task(
        client.post(
            f"/v1/voice/{uuid.uuid4()}/turn",
            files={"file": ("one.wav", b"RIFF", "audio/wav")},
        )
    )
    second = asyncio.create_task(
        client.post(
            f"/v1/voice/{uuid.uuid4()}/turn",
            files={"file": ("two.wav", b"RIFF", "audio/wav")},
        )
    )
    try:
        await _wait_for_calls(service.process_voice_turn, 2)
        rejected = await client.post(
            f"/v1/voice/{uuid.uuid4()}/turn",
            files={"file": ("three.wav", b"RIFF", "audio/wav")},
        )
        assert rejected.status_code == 429
        assert rejected.headers["retry-after"] == "3"
        assert service.process_voice_turn.await_count == 2
    finally:
        release.set()
        await asyncio.gather(first, second)
        voice_admission_controller.reset()


@pytest.mark.anyio
async def test_duplicate_request_id_is_rejected_while_original_runs(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    voice_admission_controller.reset()
    release = asyncio.Event()
    service = AsyncMock()

    async def process(**_kwargs):
        await release.wait()
        return SimpleNamespace(
            speech=SimpleNamespace(audio_content=b"wav", content_type="audio/wav"),
            message_id=uuid.uuid4(),
        )

    service.process_voice_turn.side_effect = process
    app.dependency_overrides[get_voice_service] = lambda: service
    request_id = str(uuid.uuid4())
    original = asyncio.create_task(
        client.post(
            f"/v1/voice/{uuid.uuid4()}/turn",
            headers={"X-Request-ID": request_id},
            files={"file": ("one.wav", b"RIFF", "audio/wav")},
        )
    )
    try:
        await _wait_for_calls(service.process_voice_turn, 1)
        duplicate = await client.post(
            f"/v1/voice/{uuid.uuid4()}/turn",
            headers={"X-Request-ID": request_id},
            files={"file": ("same.wav", b"RIFF", "audio/wav")},
        )
        assert duplicate.status_code == 409
        assert duplicate.headers["x-request-id"] == request_id
        assert service.process_voice_turn.await_count == 1
    finally:
        release.set()
        await original
        voice_admission_controller.reset()


@pytest.mark.anyio
async def test_internal_metrics_expose_content_free_admission_state(
    client: AsyncClient,
) -> None:
    voice_admission_controller.reset()

    response = await client.get("/internal/voice-metrics")

    assert response.status_code == 200
    assert response.json()["admission"] == {
        "active": 0,
        "capacity": 2,
        "available": 2,
        "duplicate_rejections": 0,
        "capacity_rejections": 0,
    }


@pytest.mark.anyio
async def test_stt_budget_cancels_slow_provider() -> None:
    recognition = AsyncMock()

    async def slow_transcription(_request):
        await asyncio.sleep(1)
        return TranscriptionResponse(text="late")

    recognition.transcribe_audio.side_effect = slow_transcription
    synthesis = AsyncMock()
    conversation = AsyncMock()
    conversation.get_conversation_agent = Mock(return_value=SimpleNamespace(tts_voice="xenia"))
    service = VoiceService(
        recognition,
        synthesis,
        conversation,
        execution_policy=VoiceExecutionPolicy(stt_timeout_seconds=0.01),
    )

    with pytest.raises(VoiceStageTimeoutError, match="stt"):
        await service.process_voice_turn(
            uuid.uuid4(),
            b"RIFF",
            "voice.wav",
            "audio/wav",
        )

    synthesis.synthesize_speech.assert_not_awaited()
    conversation.process_turn.assert_not_awaited()


@pytest.mark.anyio
async def test_llm_budget_stops_turn_before_tts() -> None:
    recognition = AsyncMock()
    recognition.transcribe_audio.return_value = TranscriptionResponse(text="question")
    synthesis = AsyncMock()
    conversation = AsyncMock()
    conversation.get_conversation_agent = Mock(return_value=SimpleNamespace(tts_voice="xenia"))

    async def slow_answer(**_kwargs):
        await asyncio.sleep(1)
        return SimpleNamespace(id=uuid.uuid4(), content="late")

    conversation.process_turn.side_effect = slow_answer
    service = VoiceService(
        recognition,
        synthesis,
        conversation,
        execution_policy=VoiceExecutionPolicy(llm_timeout_seconds=0.01),
    )

    with pytest.raises(VoiceStageTimeoutError, match="llm"):
        await service.process_voice_turn(
            uuid.uuid4(),
            b"RIFF",
            "voice.wav",
            "audio/wav",
        )

    synthesis.synthesize_speech.assert_not_awaited()


@pytest.mark.anyio
async def test_tts_budget_stops_slow_synthesis() -> None:
    recognition = AsyncMock()
    recognition.transcribe_audio.return_value = TranscriptionResponse(text="question")
    synthesis = AsyncMock()

    async def slow_speech(_request):
        await asyncio.sleep(1)
        return SpeechResponse(audio_content=b"late")

    synthesis.synthesize_speech.side_effect = slow_speech
    conversation = AsyncMock()
    conversation.get_conversation_agent = Mock(return_value=SimpleNamespace(tts_voice="xenia"))
    conversation.process_turn.return_value = SimpleNamespace(
        id=uuid.uuid4(),
        content="answer",
    )
    service = VoiceService(
        recognition,
        synthesis,
        conversation,
        execution_policy=VoiceExecutionPolicy(tts_timeout_seconds=0.01),
    )

    with pytest.raises(VoiceStageTimeoutError, match="tts"):
        await service.process_voice_turn(
            uuid.uuid4(),
            b"RIFF",
            "voice.wav",
            "audio/wav",
        )
