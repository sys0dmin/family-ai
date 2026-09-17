"""Read anonymized runtime metrics from Gateway and Speech Service."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from gateway.admin.voice_observability_schemas import (
    MetricsSource,
    VoiceDailyMetricResponse,
    VoiceObservabilityResponse,
)
from gateway.app.config import Settings
from gateway.app.models.voice_daily_metric import VoiceDailyMetric
from gateway.app.observability.voice_metrics_archive import VoiceMetricsArchive


class VoiceObservabilityService:
    """Aggregate runtime-only metrics without exposing service credentials."""

    def __init__(
        self,
        settings: Settings,
        archive: VoiceMetricsArchive | None = None,
    ) -> None:
        self._settings = settings
        self._archive = archive

    def get_snapshot(self) -> VoiceObservabilityResponse:
        gateway = self._fetch(
            self._settings.gateway_voice_metrics_url,
            authorization=None,
        )
        speech_url = None
        if self._settings.speech_base_url:
            speech_base = urlsplit(self._settings.speech_base_url)
            speech_url = urlunsplit(
                (
                    speech_base.scheme,
                    speech_base.netloc,
                    "/internal/metrics",
                    "",
                    "",
                )
            )
        speech_token = self._settings.speech_api_key.get_secret_value()
        speech = self._fetch(
            speech_url,
            authorization=f"Bearer {speech_token}" if speech_token else None,
        )
        history = (
            [self._history_item(item) for item in self._archive.history()]
            if self._archive is not None
            else []
        )
        return VoiceObservabilityResponse(
            gateway=gateway,
            speech=speech,
            history=history,
        )

    @staticmethod
    def _history_item(item: VoiceDailyMetric) -> VoiceDailyMetricResponse:
        def average(prefix: str) -> int | None:
            count = getattr(item, f"{prefix}_count")
            return round(getattr(item, f"{prefix}_total_ms") / count) if count else None

        return VoiceDailyMetricResponse(
            metric_date=item.metric_date,
            mode=item.mode,
            total_count=item.total_count,
            success_count=item.success_count,
            error_count=item.error_count,
            cancellation_count=item.cancellation_count,
            recording_average_ms=average("recording"),
            stt_average_ms=average("stt"),
            vision_average_ms=average("vision"),
            llm_average_ms=average("llm"),
            tts_average_ms=average("tts"),
            first_audio_average_ms=average("first_audio"),
            playback_average_ms=average("playback"),
            total_duration_average_ms=average("total_duration"),
        )

    def _fetch(self, url: str | None, authorization: str | None) -> MetricsSource:
        if not url:
            return MetricsSource(status="unconfigured", message="Endpoint is not configured")
        headers = {"Accept": "application/json"}
        if authorization:
            headers["Authorization"] = authorization
        request = Request(url, headers=headers)
        try:
            with urlopen(  # noqa: S310
                request,
                timeout=self._settings.monitoring_request_timeout_seconds,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError):
            return MetricsSource(status="down", message="Metrics endpoint is unavailable")
        if not isinstance(payload, dict):
            return MetricsSource(status="down", message="Metrics response is invalid")
        return MetricsSource(status="healthy", data=payload)
