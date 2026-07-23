"""Read anonymized runtime metrics from Gateway and Speech Service."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from gateway.admin.voice_observability_schemas import (
    MetricsSource,
    VoiceObservabilityResponse,
)
from gateway.app.config import Settings


class VoiceObservabilityService:
    """Aggregate runtime-only metrics without exposing service credentials."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

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
        return VoiceObservabilityResponse(gateway=gateway, speech=speech)

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
