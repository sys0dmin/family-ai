"""Tests for the ephemeral spoken-image conversation flow."""

import json
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from gateway.app.dependencies import (
    get_chat_provider,
    get_image_understanding_provider,
    get_speech_recognition_provider,
    get_speech_synthesis_provider,
)
from gateway.app.providers.schemas import (
    ChatResponse,
    ImageUnderstandingResponse,
    SpeechResponse,
    TranscriptionResponse,
)


def _override_providers(
    app: FastAPI,
    *,
    transcript: str = "Что это за птица?",
    observations: str = "Белая птица с серыми крыльями стоит в траве.",
    answer: str = "Похоже на чайку.",
) -> tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock]:
    chat = AsyncMock()
    chat.generate_response.return_value = ChatResponse(content=answer)
    vision = AsyncMock()
    vision.describe_image.return_value = ImageUnderstandingResponse(
        description=observations
    )
    stt = AsyncMock()
    stt.transcribe_audio.return_value = TranscriptionResponse(
        text=transcript,
        duration_ms=1400,
        confidence=0.91,
    )
    tts = AsyncMock()
    tts.synthesize_speech.return_value = SpeechResponse(
        audio_content=b"spoken-answer",
        content_type="audio/wav",
    )
    app.dependency_overrides[get_chat_provider] = lambda: chat
    app.dependency_overrides[get_image_understanding_provider] = lambda: vision
    app.dependency_overrides[get_speech_recognition_provider] = lambda: stt
    app.dependency_overrides[get_speech_synthesis_provider] = lambda: tts
    return chat, vision, stt, tts


@pytest.mark.anyio
async def test_spoken_image_turn_combines_ephemeral_inputs_and_returns_audio(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    chat, vision, stt, tts = _override_providers(app)
    created = await client.post(
        "/v1/conversations/",
        json={"agent_id": "teacher_friend"},
    )
    conversation_id = created.json()["conversation_id"]

    response = await client.post(
        f"/v1/multimodal/{conversation_id}/turn",
        data={"recording_duration_ms": "1250"},
        files={
            "image": ("bird.jpg", b"\xff\xd8\xffbird", "image/jpeg"),
            "audio": ("question.wav", b"RIFFaudio", "audio/wav"),
        },
    )

    assert response.status_code == 200
    assert response.content == b"spoken-answer"
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-family-ai-message-id"]
    assert stt.transcribe_audio.await_count == 1
    assert vision.describe_image.await_count == 1
    request_messages = chat.generate_response.await_args.args[0].messages
    assert any("Белая птица" in message.content for message in request_messages)
    tts.synthesize_speech.assert_awaited_once()

    history = await client.get(
        "/v1/conversations/latest",
        params={"agent_id": "teacher_friend"},
    )
    serialized = history.text
    assert "Что это за птица?" in serialized
    assert "Похоже на чайку." in serialized
    assert "RIFFaudio" not in serialized
    assert "bird.jpg" not in serialized


@pytest.mark.anyio
async def test_spoken_image_turn_streams_safe_audio_events(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    _override_providers(app, answer="Сначала главное. Потом подробность.")
    created = await client.post(
        "/v1/conversations/",
        json={"agent_id": "teacher_friend"},
    )

    response = await client.post(
        f"/v1/multimodal/{created.json()['conversation_id']}/turn/stream",
        files={
            "image": ("bird.jpg", b"\xff\xd8\xffbird", "image/jpeg"),
            "audio": ("question.wav", b"RIFFaudio", "audio/wav"),
        },
    )

    assert response.status_code == 200
    assert response.headers["x-family-ai-voice-protocol"] == "family-ai-voice/2"
    events = [json.loads(line) for line in response.content.splitlines()]
    assert [event["type"] for event in events] == [
        "started",
        "message",
        "audio",
        "audio",
        "complete",
    ]


@pytest.mark.anyio
async def test_spoken_image_edibility_question_uses_fixed_safety_response(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    chat, _vision, _stt, tts = _override_providers(
        app,
        transcript="Можно это съесть?",
        observations="На снимке видна неизвестная красная ягода.",
    )
    created = await client.post(
        "/v1/conversations/",
        json={"agent_id": "outdoor_guide"},
    )
    response = await client.post(
        f"/v1/multimodal/{created.json()['conversation_id']}/turn",
        files={
            "image": ("berry.png", b"\x89PNG\r\n\x1a\nberry", "image/png"),
            "audio": ("question.wav", b"RIFFaudio", "audio/wav"),
        },
    )

    assert response.status_code == 200
    chat.generate_response.assert_not_awaited()
    spoken_text = tts.synthesize_speech.await_args.args[0].text
    assert "По фотографии нельзя" in spoken_text
    assert "родителям" in spoken_text


@pytest.mark.anyio
async def test_spoken_image_electrical_question_uses_fixed_safety_response(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    chat, _vision, _stt, tts = _override_providers(
        app,
        transcript="Можно это включить?",
        observations="На снимке виден повреждённый электрический кабель.",
    )
    created = await client.post(
        "/v1/conversations/",
        json={"agent_id": "tech_guide"},
    )
    response = await client.post(
        f"/v1/multimodal/{created.json()['conversation_id']}/turn",
        files={
            "image": ("cable.jpg", b"\xff\xd8\xffcable", "image/jpeg"),
            "audio": ("question.wav", b"RIFFaudio", "audio/wav"),
        },
    )

    assert response.status_code == 200
    chat.generate_response.assert_not_awaited()
    spoken_text = tts.synthesize_speech.await_args.args[0].text
    assert "Ничего не бери и не включай" in spoken_text
    assert "родителям" in spoken_text


@pytest.mark.anyio
async def test_spoken_image_turn_rejects_agent_without_capability_before_stt(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    _chat, vision, stt, _tts = _override_providers(app)
    created = await client.post(
        "/v1/conversations/",
        json={"agent_id": "storyteller"},
    )
    response = await client.post(
        f"/v1/multimodal/{created.json()['conversation_id']}/turn",
        files={
            "image": ("photo.jpg", b"\xff\xd8\xffphoto", "image/jpeg"),
            "audio": ("question.wav", b"RIFFaudio", "audio/wav"),
        },
    )

    assert response.status_code == 403
    vision.describe_image.assert_not_awaited()
    stt.transcribe_audio.assert_not_awaited()


@pytest.mark.anyio
async def test_spoken_image_turn_rejects_unrecognized_speech(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    _chat, _vision, stt, tts = _override_providers(app, transcript="")
    created = await client.post(
        "/v1/conversations/",
        json={"agent_id": "tech_guide"},
    )
    response = await client.post(
        f"/v1/multimodal/{created.json()['conversation_id']}/turn",
        files={
            "image": ("server.webp", b"RIFFxxxxWEBPphoto", "image/webp"),
            "audio": ("question.wav", b"RIFFaudio", "audio/wav"),
        },
    )

    assert response.status_code == 422
    assert stt.transcribe_audio.await_count == 1
    tts.synthesize_speech.assert_not_awaited()


@pytest.mark.anyio
async def test_spoken_image_turn_rejects_unsupported_image_before_providers(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    _chat, vision, stt, _tts = _override_providers(app)
    response = await client.post(
        "/v1/multimodal/00000000-0000-0000-0000-000000000001/turn",
        files={
            "image": ("note.txt", b"not-image", "text/plain"),
            "audio": ("question.wav", b"RIFFaudio", "audio/wav"),
        },
    )

    assert response.status_code == 415
    vision.describe_image.assert_not_awaited()
    stt.transcribe_audio.assert_not_awaited()
