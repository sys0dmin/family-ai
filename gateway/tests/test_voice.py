"""Tests for the server-side voice conversation flow."""

import uuid
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from gateway.app.dependencies import get_voice_service
from gateway.app.providers.openai import OpenAIProvider
from gateway.app.providers.schemas import (
    SpeechRequest,
    SpeechResponse,
    TranscriptionRequest,
    TranscriptionResponse,
)
from gateway.app.services.music_recognition_service import MusicRecognitionContext
from gateway.app.services.voice_service import VoiceService, VoiceTurnResult


@pytest.mark.anyio
async def test_openai_provider_returns_configured_wav_content_type() -> None:
    provider = OpenAIProvider(
        api_key="test-chat-key",
        speech_api_key="test-speech-key",
        tts_model="canopylabs/orpheus-arabic-saudi",
        tts_voice="lulwa",
        tts_response_format="wav",
    )
    speech_create = AsyncMock(return_value=SimpleNamespace(content=b"wav-audio"))
    provider._speech_client = SimpleNamespace(
        audio=SimpleNamespace(
            speech=SimpleNamespace(create=speech_create),
        )
    )

    response = await provider.synthesize_speech(SpeechRequest(text="Привет!"))

    assert response.audio_content == b"wav-audio"
    assert response.content_type == "audio/wav"
    speech_create.assert_awaited_once_with(
        model="canopylabs/orpheus-arabic-saudi",
        voice="lulwa",
        input="Привет!",
        response_format="wav",
    )


@pytest.mark.anyio
async def test_openai_provider_uses_deterministic_stt_temperature() -> None:
    provider = OpenAIProvider(
        api_key="test-chat-key",
        speech_api_key="test-speech-key",
        stt_model="whisper-large-v3-turbo",
        stt_temperature=0.0,
    )
    transcription_create = AsyncMock(return_value="Привет")
    provider._speech_client = SimpleNamespace(
        audio=SimpleNamespace(
            transcriptions=SimpleNamespace(create=transcription_create),
        )
    )

    response = await provider.transcribe_audio(
        TranscriptionRequest(
            audio_content=b"wav-audio",
            filename="recording.wav",
            content_type="audio/wav",
            language="ru",
        )
    )

    assert response.text == "Привет"
    transcription_create.assert_awaited_once_with(
        model="whisper-large-v3-turbo",
        file=("recording.wav", b"wav-audio", "audio/wav"),
        language="ru",
        response_format="verbose_json",
        temperature=0.0,
    )


@pytest.mark.anyio
async def test_openai_provider_normalizes_verbose_stt_diagnostics() -> None:
    provider = OpenAIProvider(
        api_key="test-chat-key",
        speech_api_key="test-speech-key",
        stt_initial_prompt="Лера, Мурка, Байтик",
    )
    transcription_create = AsyncMock(
        return_value=SimpleNamespace(
            text="Привет, Байтик",
            duration=2.4,
            segments=[
                SimpleNamespace(
                    start=0.2,
                    end=2.0,
                    avg_logprob=-0.1,
                    no_speech_prob=0.02,
                )
            ],
        )
    )
    provider._speech_client = SimpleNamespace(
        audio=SimpleNamespace(
            transcriptions=SimpleNamespace(create=transcription_create),
        )
    )

    response = await provider.transcribe_audio(
        TranscriptionRequest(
            audio_content=b"wav-audio",
            filename="recording.wav",
            content_type="audio/wav",
        )
    )

    assert response.text == "Привет, Байтик"
    assert response.duration_ms == 2400
    assert response.speech_duration_ms == 1800
    assert response.confidence == pytest.approx(0.9048, abs=0.0001)
    assert response.no_speech_probability == 0.02
    assert transcription_create.await_args.kwargs["prompt"] == "Лера, Мурка, Байтик"


@pytest.mark.anyio
async def test_voice_service_preserves_recording_metadata() -> None:
    provider = AsyncMock()
    provider.transcribe_audio.return_value = TranscriptionResponse(text="Привет")
    provider.synthesize_speech.return_value = SpeechResponse(audio_content=b"mp3")
    conversation_service = AsyncMock()
    message_id = uuid.uuid4()
    conversation_service.process_turn.return_value = SimpleNamespace(
        id=message_id,
        content="Привет, Лера!",
    )
    conversation_service.get_conversation_agent = Mock(
        return_value=SimpleNamespace(tts_voice="lulwa")
    )
    service = VoiceService(provider, conversation_service)
    conversation_id = uuid.uuid4()

    result = await service.process_voice_turn(
        conversation_id=conversation_id,
        audio_content=b"webm-audio",
        filename="recording.webm",
        content_type="audio/webm",
    )

    assert result.speech.audio_content == b"mp3"
    assert result.message_id == message_id
    provider.transcribe_audio.assert_awaited_once_with(
        TranscriptionRequest(
            audio_content=b"webm-audio",
            filename="recording.webm",
            content_type="audio/webm",
            language="ru",
        )
    )
    conversation_service.process_turn.assert_awaited_once_with(
        conversation_id=conversation_id,
        text="Привет",
        runtime_context=None,
        diagnostics=ANY,
    )
    provider.synthesize_speech.assert_awaited_once_with(
        SpeechRequest(text="Привет, Лера!", voice="lulwa")
    )


@pytest.mark.anyio
async def test_voice_service_uses_melody_context_when_humming_has_no_words() -> None:
    provider = AsyncMock()
    provider.transcribe_audio.return_value = TranscriptionResponse(text="")
    provider.synthesize_speech.return_value = SpeechResponse(audio_content=b"wav")
    conversation_service = AsyncMock()
    conversation_service.process_turn.return_value = SimpleNamespace(
        id=uuid.uuid4(),
        content="Кажется, это песня!",
    )
    agent = SimpleNamespace(tts_voice="lulwa", tools=("music_recognition",))
    conversation_service.get_conversation_agent = Mock(return_value=agent)
    recognition_service = AsyncMock()
    recognition_service.recognize_for_agent.return_value = MusicRecognitionContext(
        prompt_context="Вариант 1: название='Тест'"
    )
    service = VoiceService(provider, conversation_service, recognition_service)
    conversation_id = uuid.uuid4()

    await service.process_voice_turn(
        conversation_id=conversation_id,
        audio_content=b"humming",
        filename="recording.webm",
        content_type="audio/webm",
    )

    recognition_service.recognize_for_agent.assert_awaited_once_with(
        agent=agent,
        audio_content=b"humming",
        filename="recording.webm",
        content_type="audio/webm",
    )
    conversation_service.process_turn.assert_awaited_once_with(
        conversation_id=conversation_id,
        text="[Лера напела мелодию без слов]",
        runtime_context="Вариант 1: название='Тест'",
        diagnostics=ANY,
    )


@pytest.mark.anyio
async def test_voice_service_synthesizes_text_with_conversation_agent_voice() -> None:
    provider = AsyncMock()
    provider.synthesize_speech.return_value = SpeechResponse(audio_content=b"wav")
    conversation_service = Mock()
    conversation_service.get_conversation_agent.return_value = SimpleNamespace(
        tts_voice="noura"
    )
    service = VoiceService(provider, conversation_service)
    conversation_id = uuid.uuid4()

    response = await service.synthesize_text(conversation_id, "  Привет!  ")

    assert response.audio_content == b"wav"
    provider.synthesize_speech.assert_awaited_once_with(
        SpeechRequest(text="Привет!", voice="noura")
    )


@pytest.mark.anyio
async def test_voice_endpoint_returns_provider_content_type(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    voice_service = AsyncMock()
    message_id = uuid.uuid4()
    voice_service.process_voice_turn.return_value = VoiceTurnResult(
        speech=SpeechResponse(
            audio_content=b"audio-response",
            content_type="audio/mpeg",
        ),
        message_id=message_id,
    )
    app.dependency_overrides[get_voice_service] = lambda: voice_service
    conversation_id = uuid.uuid4()

    response = await client.post(
        f"/v1/voice/{conversation_id}/turn",
        files={"file": ("recording.webm", b"webm-audio", "audio/webm;codecs=opus")},
        data={"recording_duration_ms": "1250"},
    )

    assert response.status_code == 200
    assert response.content == b"audio-response"
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-family-ai-message-id"] == str(message_id)
    voice_service.process_voice_turn.assert_awaited_once_with(
        conversation_id=conversation_id,
        audio_content=b"webm-audio",
        filename="recording.webm",
        content_type="audio/webm",
        language="ru",
        recording_duration_ms=1250,
    )


@pytest.mark.anyio
async def test_synthesize_endpoint_returns_agent_audio(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    voice_service = AsyncMock()
    voice_service.synthesize_text.return_value = SpeechResponse(
        audio_content=b"agent-voice",
        content_type="audio/wav",
    )
    app.dependency_overrides[get_voice_service] = lambda: voice_service
    conversation_id = uuid.uuid4()

    response = await client.post(
        f"/v1/voice/{conversation_id}/synthesize",
        json={"text": "Привет, Лера!"},
    )

    assert response.status_code == 200
    assert response.content == b"agent-voice"
    assert response.headers["content-type"] == "audio/wav"
    voice_service.synthesize_text.assert_awaited_once_with(
        conversation_id,
        "Привет, Лера!",
    )


@pytest.mark.anyio
async def test_voice_endpoint_rejects_non_audio(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    voice_service = AsyncMock()
    app.dependency_overrides[get_voice_service] = lambda: voice_service

    response = await client.post(
        f"/v1/voice/{uuid.uuid4()}/turn",
        files={"file": ("payload.txt", b"not-audio", "text/plain")},
    )

    assert response.status_code == 415
    voice_service.process_voice_turn.assert_not_awaited()
