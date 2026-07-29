"""Tests for privacy-preserving voice pipeline metrics."""

from gateway.app.observability.voice_metrics import VoiceMetricsRegistry


def test_voice_metrics_summarize_stages_and_errors_without_content() -> None:
    registry = VoiceMetricsRegistry(max_samples=2)
    registry.record(
        status="success",
        recording_duration_ms=2100,
        stt_duration_ms=900,
        llm_duration_ms=1200,
        vision_duration_ms=600,
        tts_duration_ms=700,
        total_duration_ms=2800,
        stt_confidence=0.84,
    )
    registry.record(
        status="error",
        error_stage="tts",
        recording_duration_ms=1800,
        stt_duration_ms=800,
        llm_duration_ms=1000,
        total_duration_ms=1900,
    )

    snapshot = registry.snapshot()

    assert snapshot["window_size"] == 2
    assert snapshot["successes"] == 1
    assert snapshot["errors"] == 1
    assert snapshot["error_stages"] == {"tts": 1}
    assert snapshot["stages"]["stt"]["last_ms"] == 800
    assert snapshot["stages"]["vision"]["last_ms"] == 600
    assert snapshot["recent"][0]["mode"] == "voice"
    assert "text" not in str(snapshot)
    assert "conversation_id" not in str(snapshot)
