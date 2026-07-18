"""Tests for the server-side voice conversation flow."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

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
from gateway.app.services.voice_service import VoiceService


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
        response_format="text",
        temperature=0.0,
    )


@pytest.mark.anyio
async def test_voice_service_preserves_recording_metadata() -> None:
    provider = AsyncMock()
    provider.transcribe_audio.return_value = TranscriptionResponse(text="Привет")
    provider.synthesize_speech.return_value = SpeechResponse(audio_content=b"mp3")
    conversation_service = AsyncMock()
    conversation_service.process_turn.return_value = SimpleNamespace(content="Привет, Лера!")
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

    assert result.audio_content == b"mp3"
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
    conversation_service.process_turn.return_value = SimpleNamespace(content="Кажется, это песня!")
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
    voice_service.process_voice_turn.return_value = SpeechResponse(
        audio_content=b"audio-response",
        content_type="audio/mpeg",
    )
    app.dependency_overrides[get_voice_service] = lambda: voice_service
    conversation_id = uuid.uuid4()

    response = await client.post(
        f"/v1/voice/{conversation_id}/turn",
        files={"file": ("recording.webm", b"webm-audio", "audio/webm;codecs=opus")},
    )

    assert response.status_code == 200
    assert response.content == b"audio-response"
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.headers["cache-control"] == "no-store"
    voice_service.process_voice_turn.assert_awaited_once_with(
        conversation_id=conversation_id,
        audio_content=b"webm-audio",
        filename="recording.webm",
        content_type="audio/webm",
        language="ru",
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
