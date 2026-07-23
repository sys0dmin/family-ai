"""Runtime queue metrics for serialized local inference."""

import pytest

from family_ai_speech.backends import TranscriptionResult
from family_ai_speech.service import LocalSpeechService


class BlockingStt:
    def transcribe(
        self,
        _audio: bytes,
        language: str,
        _prompt: str | None = None,
    ) -> TranscriptionResult:
        return TranscriptionResult(
            text="Привет",
            language=language,
            duration_seconds=1,
            speech_duration_seconds=1,
            confidence=0.9,
            no_speech_probability=0.01,
            segments=(),
        )


class FakeTts:
    def synthesize(self, _text: str, _voice: str | None) -> bytes:
        return b"wav"


@pytest.mark.anyio
async def test_runtime_metrics_count_stt_and_tts_calls() -> None:
    service = LocalSpeechService(BlockingStt(), FakeTts())

    transcription = await service.transcribe(b"wav", "ru", "Лера")
    audio = await service.synthesize("Привет", "xenia")
    snapshot = service.metrics_snapshot()

    assert transcription.text == "Привет"
    assert audio == b"wav"
    assert snapshot.queue_depth == 0
    assert snapshot.active_stage is None
    assert snapshot.stt.calls == 1
    assert snapshot.tts.calls == 1
    assert snapshot.stt.errors == 0
