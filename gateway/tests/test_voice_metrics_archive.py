"""Tests for durable, content-free voice operation aggregates."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from gateway.app.observability.voice_metrics import VoiceTurnSample
from gateway.app.observability.voice_metrics_archive import VoiceMetricsArchive


def _sample(*, mode: str = "voice", status: str = "success") -> VoiceTurnSample:
    return VoiceTurnSample(
        timestamp=datetime.now(UTC).isoformat(),
        mode=mode,
        status=status,
        recording_duration_ms=1200,
        stt_duration_ms=900,
        vision_duration_ms=None,
        llm_duration_ms=1100,
        tts_duration_ms=700,
        total_duration_ms=3900,
        first_audio_ready_ms=2400,
        client_first_playback_ms=2600,
        cancelled=False,
    )


def test_archive_aggregates_daily_durations_without_turn_content(
    session_factory: sessionmaker[Session],
) -> None:
    archive = VoiceMetricsArchive(lambda: session_factory)

    archive.record(_sample())
    archive.record(_sample(status="error"))
    archive.record(_sample(mode="speech_replay"))

    rows = archive.history()

    voice = next(row for row in rows if row.mode == "voice")
    replay = next(row for row in rows if row.mode == "speech_replay")
    assert voice.total_count == 2
    assert voice.success_count == 1
    assert voice.error_count == 1
    assert voice.stt_count == 2
    assert voice.stt_total_ms == 1800
    assert replay.total_count == 1
    assert replay.tts_total_ms == 700
    assert not hasattr(voice, "conversation_id")
    assert not hasattr(voice, "text")


def test_archive_adds_late_playback_without_counting_turn_twice(
    session_factory: sessionmaker[Session],
) -> None:
    archive = VoiceMetricsArchive(lambda: session_factory)
    sample = _sample()
    archive.record(sample)
    archive.record_playback(
        VoiceTurnSample(**{**sample.__dict__, "client_first_playback_ms": 3000})
    )

    row = next(item for item in archive.history() if item.mode == "voice")
    assert row.total_count == 1
    assert row.playback_count == 2
    assert row.playback_total_ms == 5600
