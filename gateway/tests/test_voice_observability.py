"""Tests for Admin aggregation of private voice metrics."""

from unittest.mock import Mock

from gateway.admin.voice_observability_schemas import MetricsSource
from gateway.admin.voice_observability_service import VoiceObservabilityService
from gateway.app.config import Settings


def test_speech_metrics_url_is_resolved_from_openai_v1_base() -> None:
    settings = Settings(
        speech_base_url="http://speech.local:8010/v1",
        speech_api_key="speech-secret",
    )
    service = VoiceObservabilityService(settings)
    service._fetch = Mock(return_value=MetricsSource(status="healthy", data={}))

    service.get_snapshot()

    assert service._fetch.call_args_list[1].args == (
        "http://speech.local:8010/internal/metrics",
    )
    assert service._fetch.call_args_list[1].kwargs == {
        "authorization": "Bearer speech-secret"
    }
