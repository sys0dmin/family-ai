"""HTTP contract tests for the local speech service."""

from pydantic import SecretStr
from starlette.testclient import TestClient

from family_ai_speech.config import SpeechSettings
from family_ai_speech.main import create_app


class FakeSpeechService:
    def __init__(self) -> None:
        self.transcriptions: list[tuple[bytes, str]] = []
        self.syntheses: list[tuple[str, str | None]] = []

    async def transcribe(self, audio: bytes, language: str) -> str:
        self.transcriptions.append((audio, language))
        return "Привет"

    async def synthesize(self, text: str, voice: str | None) -> bytes:
        self.syntheses.append((text, voice))
        return b"RIFF-local-wav"


def build_client() -> tuple[TestClient, FakeSpeechService]:
    settings = SpeechSettings(
        api_key=SecretStr("local-secret"),
        stt_model="base",
        tts_model="silero-v5_2-ru",
        max_audio_bytes=1024,
    )
    service = FakeSpeechService()
    return TestClient(create_app(settings=settings, service=service)), service


def test_health_does_not_require_authentication() -> None:
    client, _service = build_client()

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["service"] == "family-ai-speech"


def test_transcription_matches_openai_text_contract() -> None:
    client, service = build_client()

    response = client.post(
        "/v1/audio/transcriptions",
        headers={"Authorization": "Bearer local-secret"},
        data={"model": "base", "language": "ru", "response_format": "text"},
        files={"file": ("voice.wav", b"RIFF", "audio/wav")},
    )

    assert response.status_code == 200
    assert response.text == "Привет"
    assert service.transcriptions == [(b"RIFF", "ru")]


def test_synthesis_returns_wav() -> None:
    client, service = build_client()

    response = client.post(
        "/v1/audio/speech",
        headers={"Authorization": "Bearer local-secret"},
        json={
            "model": "silero-v5_2-ru",
            "voice": "lulwa",
            "response_format": "wav",
            "input": "Привет!",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == b"RIFF-local-wav"
    assert service.syntheses == [("Привет!", "lulwa")]


def test_audio_endpoints_require_bearer_token() -> None:
    client, _service = build_client()

    response = client.post(
        "/v1/audio/speech",
        json={
            "model": "silero-v5_2-ru",
            "voice": "xenia",
            "response_format": "wav",
            "input": "Привет!",
        },
    )

    assert response.status_code == 401


def test_transcription_rejects_oversized_audio() -> None:
    client, service = build_client()

    response = client.post(
        "/v1/audio/transcriptions",
        headers={"Authorization": "Bearer local-secret"},
        data={"model": "base"},
        files={"file": ("voice.wav", b"x" * 1025, "audio/wav")},
    )

    assert response.status_code == 413
    assert service.transcriptions == []
