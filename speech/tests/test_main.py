"""HTTP contract tests for the local speech service."""

from datetime import UTC, datetime
from pathlib import Path
from tempfile import mkdtemp

from pydantic import SecretStr
from starlette.testclient import TestClient

from family_ai_speech.backends import TranscriptionResult, TranscriptionSegment
from family_ai_speech.config import SpeechSettings
from family_ai_speech.main import create_app
from family_ai_speech.schemas import SpeechRuntimeMetricsResponse, StageRuntimeMetrics


class FakeSpeechService:
    def __init__(self) -> None:
        self.transcriptions: list[tuple[bytes, str, str | None]] = []
        self.syntheses: list[tuple[str, str | None]] = []

    async def transcribe(
        self,
        audio: bytes,
        language: str,
        prompt: str | None = None,
    ) -> TranscriptionResult:
        self.transcriptions.append((audio, language, prompt))
        return TranscriptionResult(
            text="Привет",
            language="ru",
            duration_seconds=1.2,
            speech_duration_seconds=0.8,
            confidence=0.91,
            no_speech_probability=0.02,
            segments=(
                TranscriptionSegment(
                    id=0,
                    start=0.1,
                    end=0.9,
                    text="Привет",
                    avg_logprob=-0.09,
                    no_speech_probability=0.02,
                ),
            ),
        )

    async def synthesize(self, text: str, voice: str | None) -> bytes:
        self.syntheses.append((text, voice))
        return b"RIFF-local-wav"

    async def benchmark_transcribe(
        self,
        audio: bytes,
        language: str,
        prompt: str | None,
        *,
        beam_size: int,
        vad_filter: bool,
    ) -> TranscriptionResult:
        del beam_size, vad_filter
        return await self.transcribe(audio, language, prompt)

    def metrics_snapshot(self) -> SpeechRuntimeMetricsResponse:
        empty_stage = StageRuntimeMetrics(
            calls=0,
            errors=0,
            average_processing_ms=None,
            last_processing_ms=None,
            average_queue_wait_ms=None,
            last_queue_wait_ms=None,
        )
        return SpeechRuntimeMetricsResponse(
            generated_at=datetime.now(UTC),
            uptime_seconds=10,
            queue_depth=0,
            active_stage=None,
            stt=empty_stage,
            tts=empty_stage,
        )


def build_client() -> tuple[TestClient, FakeSpeechService]:
    settings = SpeechSettings(
        api_key=SecretStr("local-secret"),
        stt_model="base",
        tts_model="silero-v5_2-ru",
        max_audio_bytes=1024,
        calibration_dir=Path(mkdtemp(prefix="family-ai-calibration-test-")),
    )
    service = FakeSpeechService()
    return TestClient(create_app(settings=settings, service=service)), service


def test_health_does_not_require_authentication() -> None:
    client, _service = build_client()

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["service"] == "family-ai-speech"


def test_calibration_samples_stay_behind_private_authentication() -> None:
    client, _service = build_client()

    denied = client.post(
        "/internal/calibrations",
        json={
            "prompts": [
                {
                    "id": "speech_01",
                    "expected_text": "Привет, Лера",
                    "kind": "speech",
                }
            ],
            "initial_prompt": "Лера",
        },
    )
    assert denied.status_code == 401

    started = client.post(
        "/internal/calibrations",
        headers={"Authorization": "Bearer local-secret"},
        json={
            "prompts": [
                {
                    "id": "speech_01",
                    "expected_text": "Привет, Лера",
                    "kind": "speech",
                }
            ],
            "initial_prompt": "Лера",
        },
    )
    assert started.status_code == 201
    session_id = started.json()["id"]

    uploaded = client.post(
        f"/internal/calibrations/{session_id}/samples/speech_01",
        headers={"Authorization": "Bearer local-secret"},
        files={"file": ("sample.wav", b"RIFF", "audio/wav")},
    )
    assert uploaded.status_code == 204

    cancelled = client.delete(
        f"/internal/calibrations/{session_id}",
        headers={"Authorization": "Bearer local-secret"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_transcription_matches_openai_text_contract() -> None:
    client, service = build_client()

    response = client.post(
        "/v1/audio/transcriptions",
        headers={"Authorization": "Bearer local-secret"},
        data={
            "model": "base",
            "language": "ru",
            "response_format": "text",
            "prompt": "Лера, Мурка",
        },
        files={"file": ("voice.wav", b"RIFF", "audio/wav")},
    )

    assert response.status_code == 200
    assert response.text == "Привет"
    assert service.transcriptions == [(b"RIFF", "ru", "Лера, Мурка")]


def test_transcription_returns_openai_verbose_diagnostics() -> None:
    client, _service = build_client()

    response = client.post(
        "/v1/audio/transcriptions",
        headers={"Authorization": "Bearer local-secret"},
        data={"model": "base", "language": "ru", "response_format": "verbose_json"},
        files={"file": ("voice.wav", b"RIFF", "audio/wav")},
    )

    assert response.status_code == 200
    assert response.json()["duration"] == 1.2
    assert response.json()["segments"][0]["avg_logprob"] == -0.09
    assert response.json()["segments"][0]["no_speech_prob"] == 0.02


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


def test_internal_metrics_require_bearer_token() -> None:
    client, _service = build_client()

    denied = client.get("/internal/metrics")
    allowed = client.get(
        "/internal/metrics",
        headers={"Authorization": "Bearer local-secret"},
    )

    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["queue_depth"] == 0


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
