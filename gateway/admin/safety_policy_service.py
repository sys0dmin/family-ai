"""Loopback adapter for Gateway-owned Safety Policy runtime state."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from gateway.admin.safety_policy_schemas import (
    SafetyPolicySnapshot,
    SafetyScenarioReport,
)
from gateway.app.config import Settings


class SafetyPolicyAdminError(RuntimeError):
    """Raised when Gateway policy state is unavailable."""


class SafetyPolicyAdminService:
    def __init__(self, settings: Settings) -> None:
        self._url = settings.gateway_safety_policy_url
        self._timeout = settings.monitoring_request_timeout_seconds

    def snapshot(self) -> SafetyPolicySnapshot:
        return SafetyPolicySnapshot.model_validate(self._request("GET"))

    def reset_metrics(self) -> SafetyPolicySnapshot:
        return SafetyPolicySnapshot.model_validate(
            self._request("DELETE", "/metrics")
        )

    def run_scenarios(self) -> SafetyScenarioReport:
        return SafetyScenarioReport.model_validate(
            self._request("POST", "/scenarios")
        )

    def _request(self, method: str, suffix: str = "") -> dict[str, object]:
        if not self._url:
            raise SafetyPolicyAdminError("Safety Policy endpoint is not configured")
        request = Request(
            self._url.rstrip("/") + suffix,
            method=method,
            headers={"Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, OSError, TimeoutError, ValueError) as exc:
            raise SafetyPolicyAdminError("Safety Policy endpoint is unavailable") from exc
        if not isinstance(payload, dict):
            raise SafetyPolicyAdminError("Safety Policy response is invalid")
        return payload
