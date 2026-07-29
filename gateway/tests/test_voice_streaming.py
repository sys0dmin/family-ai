"""Tests for the provider-neutral Voice 2.0 event protocol."""

import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gateway.app.observability.voice_metrics import VoiceMetricsRegistry
from gateway.app.providers.schemas import SpeechResponse, TranscriptionResponse
from gateway.app.services.voice_service import VoiceService
from gateway.app.services.voice_streaming import (
    VoiceStreamRegistry,
    split_speech_chunks,
)


def test_speech_chunks_put_a_short_natural_unit_first() -> None:
    text = (
        "Сначала главное предупреждение. "
        "Потом идёт более подробное объяснение, которое можно слушать спокойно. "
        + "Очень длинная часть " * 30
    )

    chunks = split_speech_chunks(text)

    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")
    assert len(chunks[0]) <= 180
    assert all(len(chunk) <= 320 for chunk in chunks[1:])
    assert chunks[0].endswith("предупреждение.")


@pytest.mark.anyio
async def test_voice_stream_yields_message_before_sequential_audio_parts() -> None:
    recognition = AsyncMock()
    recognition.transcribe_audio.return_value = TranscriptionResponse(
        text="Расскажи о памяти"
    )
    synthesis = AsyncMock()
    synthesis.synthesize_speech.side_effect = (
        SpeechResponse(audio_content=b"part-one", content_type="audio/wav"),
        SpeechResponse(audio_content=b"part-two", content_type="audio/wav"),
    )
    conversation = AsyncMock()
    message_id = uuid.uuid4()
    conversation.get_conversation_agent = Mock(
        return_value=SimpleNamespace(tts_voice="baya")
    )
    conversation.process_turn.return_value = SimpleNamespace(
        id=message_id,
        content=(
            "Память помогает компьютеру держать нужные данные рядом. "
            + "Следующее объяснение " * 8
        ),
    )
    metrics = VoiceMetricsRegistry()
    service = VoiceService(
        recognition,
        synthesis,
        conversation,
        metrics=metrics,
    )

    events = [
        json.loads(event)
        async for event in service.stream_voice_turn(
            uuid.uuid4(),
            b"RIFFaudio",
            "voice.wav",
            "audio/wav",
        )
    ]

    assert [event["type"] for event in events] == [
        "started",
        "message",
        "audio",
        "audio",
        "complete",
    ]
    assert events[1]["message_id"] == str(message_id)
    assert events[1]["chunk_count"] == 2
    assert synthesis.synthesize_speech.await_count == 2
    assert all(
        event["protocol"] == "family-ai-voice/2"
        for event in events
    )
    snapshot = metrics.snapshot()
    assert snapshot["successes"] == 1
    assert snapshot["recent"][0]["streamed"] is True
    assert snapshot["recent"][0]["chunk_count"] == 2


@pytest.mark.anyio
async def test_stream_registry_cancels_registered_request_task() -> None:
    registry = VoiceStreamRegistry()
    turn_id = uuid.uuid4()
    ready = asyncio.Event()

    async def wait_forever() -> None:
        registry.register(turn_id)
        ready.set()
        try:
            await asyncio.Event().wait()
        finally:
            registry.unregister(turn_id)

    task = asyncio.create_task(wait_forever())
    await ready.wait()

    assert registry.cancel(turn_id) is True
    with pytest.raises(asyncio.CancelledError):
        await task
    assert registry.cancel(turn_id) is False


def test_client_playback_metric_can_arrive_before_or_after_completion() -> None:
    registry = VoiceMetricsRegistry()
    registry.report_client_playback("early", 1450)
    registry.record(
        turn_id="early",
        streamed=True,
        status="success",
        total_duration_ms=2000,
    )
    registry.record(
        turn_id="late",
        streamed=True,
        status="success",
        total_duration_ms=2300,
    )
    registry.report_client_playback("late", 1700)

    recent = registry.snapshot()["recent"]
    assert recent[0]["client_first_playback_ms"] == 1450
    assert recent[1]["client_first_playback_ms"] == 1700
    assert all("turn_id" not in sample for sample in recent)
