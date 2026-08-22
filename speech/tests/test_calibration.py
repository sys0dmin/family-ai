"""Tests for temporary local STT calibration lifecycle."""

from pathlib import Path

import pytest

from family_ai_speech.backends import TranscriptionResult
from family_ai_speech.calibration import (
    CalibrationManager,
    select_recommended_configuration,
)
from family_ai_speech.schemas import CalibrationConfigurationResult, CalibrationPrompt


class FakeBenchmarkSpeechService:
    async def benchmark_transcribe(
        self,
        audio: bytes,
        _language: str,
        _prompt: str | None,
        *,
        beam_size: int,
        vad_filter: bool,
    ) -> TranscriptionResult:
        del beam_size, vad_filter
        text = "Привет Лера" if audio == b"speech" else ""
        return TranscriptionResult(
            text=text,
            language="ru",
            duration_seconds=1,
            speech_duration_seconds=1 if text else 0,
            confidence=0.9 if text else None,
            no_speech_probability=0.01 if text else 0.99,
            segments=(),
        )


def test_recommendation_accepts_small_accuracy_tradeoff_for_lower_p95() -> None:
    def result(beam: int, accuracy: float, p95: float) -> CalibrationConfigurationResult:
        return CalibrationConfigurationResult(
            beam_size=beam,
            vad_filter=True,
            spoken_accuracy_percent=accuracy,
            silence_rejection_percent=100,
            average_processing_ms=p95 - 500,
            p95_processing_ms=p95,
            average_confidence=0.5,
        )

    recommended = select_recommended_configuration(
        [
            result(1, 45.5, 11812.6),
            result(3, 50.0, 9553.8),
            result(5, 53.0, 10400.9),
        ]
    )

    assert recommended.beam_size == 3


@pytest.mark.anyio
async def test_calibration_runs_all_options_and_deletes_audio(tmp_path: Path) -> None:
    manager = CalibrationManager(
        tmp_path,
        expiry_hours=24,
        speech_service=FakeBenchmarkSpeechService(),
    )
    state = manager.start(
        [
            CalibrationPrompt(id="speech_01", expected_text="Привет Лера", kind="speech"),
            CalibrationPrompt(id="silence_01", expected_text="", kind="silence"),
        ],
        "Лера",
    )
    manager.add_sample(state.id, "speech_01", b"speech")
    manager.add_sample(state.id, "silence_01", b"silence")

    manager.complete(state.id)
    assert manager._task is not None
    await manager._task
    result = manager.current()

    assert result.status == "completed"
    assert len(result.results) == 6
    assert result.current_trial == 12
    assert result.samples_collected == 2
    assert result.recommended_beam_size in {1, 3, 5}
    assert result.recommended_vad_filter is True
    assert not (tmp_path / state.id).exists()
