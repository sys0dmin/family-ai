"""Tests for the narrowly-scoped persistent Speech runtime settings."""

from pathlib import Path

import pytest

from family_ai_speech.runtime_settings import (
    RuntimeSettingsApplyError,
    SpeechRuntimeSettingsManager,
)


def test_runtime_settings_are_written_atomically(tmp_path: Path) -> None:
    restarts = []
    path = tmp_path / "runtime.env"
    manager = SpeechRuntimeSettingsManager(
        path,
        tmp_path / "restart.request",
        lambda: restarts.append(True),
    )

    manager.apply(beam_size=5, vad_filter=True)

    assert path.read_text(encoding="utf-8") == (
        "FAMILY_AI_SPEECH_STT_BEAM_SIZE=5\n"
        "FAMILY_AI_SPEECH_STT_VAD_FILTER=true\n"
    )
    assert restarts == [True]


def test_default_scheduler_creates_only_fixed_restart_request(tmp_path: Path) -> None:
    restart_request = tmp_path / "restart.request"
    manager = SpeechRuntimeSettingsManager(
        tmp_path / "runtime.env",
        restart_request,
    )

    manager.apply(beam_size=1, vad_filter=False)

    assert restart_request.is_file()


def test_runtime_settings_roll_back_when_restart_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "runtime.env"
    path.write_text("previous=true\n", encoding="utf-8")

    def reject_restart() -> None:
        raise RuntimeSettingsApplyError("rejected")

    manager = SpeechRuntimeSettingsManager(
        path,
        tmp_path / "restart.request",
        reject_restart,
    )

    with pytest.raises(RuntimeSettingsApplyError):
        manager.apply(beam_size=3, vad_filter=False)

    assert path.read_text(encoding="utf-8") == "previous=true\n"
