"""Gateway adapter for the private Speech Service calibration API."""

from urllib.parse import urlsplit, urlunsplit

import httpx

from gateway.app.calibration.prompts import CALIBRATION_PROMPTS
from gateway.app.calibration.schemas import CalibrationStatusResponse
from gateway.app.config import Settings


class CalibrationUnavailableError(RuntimeError):
    """Raised when Speech calibration cannot be reached or completed."""


class SpeechCalibrationService:
    """Keep Speech-specific HTTP details outside Admin and child transports."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = self._resolve_base_url(settings.speech_base_url)

    async def start(self) -> CalibrationStatusResponse:
        payload = {
            "prompts": [
                {
                    "id": prompt.id,
                    "expected_text": prompt.expected_text,
                    "kind": prompt.kind,
                }
                for prompt in CALIBRATION_PROMPTS
            ],
            "initial_prompt": self._settings.stt_initial_prompt,
        }
        return await self._request("POST", "/internal/calibrations", json=payload)

    async def current(self) -> CalibrationStatusResponse | None:
        return await self._request(
            "GET",
            "/internal/calibrations/current",
            allow_not_found=True,
        )

    async def add_sample(
        self,
        session_id: str,
        prompt_id: str,
        audio: bytes,
        content_type: str,
    ) -> None:
        await self._request(
            "POST",
            f"/internal/calibrations/{session_id}/samples/{prompt_id}",
            files={"file": ("calibration.wav", audio, content_type)},
            expect_empty=True,
        )

    async def complete(self, session_id: str) -> CalibrationStatusResponse:
        return await self._request(
            "POST",
            f"/internal/calibrations/{session_id}/complete",
        )

    async def cancel(self, session_id: str) -> CalibrationStatusResponse:
        return await self._request(
            "DELETE",
            f"/internal/calibrations/{session_id}",
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        allow_not_found: bool = False,
        expect_empty: bool = False,
        **kwargs,
    ):
        if self._base_url is None:
            raise CalibrationUnavailableError("Local Speech Service is not configured")
        headers = kwargs.pop("headers", {})
        token = self._settings.speech_api_key.get_secret_value()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with httpx.AsyncClient(
                timeout=self._settings.calibration_request_timeout_seconds
            ) as client:
                response = await client.request(
                    method,
                    self._base_url + path,
                    headers=headers,
                    **kwargs,
                )
        except httpx.HTTPError as exc:
            raise CalibrationUnavailableError("Speech calibration is unavailable") from exc
        if allow_not_found and response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise CalibrationUnavailableError(
                f"Speech calibration returned HTTP {response.status_code}"
            )
        if expect_empty:
            return None
        return CalibrationStatusResponse.model_validate(response.json())

    @staticmethod
    def _resolve_base_url(speech_base_url: str | None) -> str | None:
        if not speech_base_url:
            return None
        parsed = urlsplit(speech_base_url)
        return urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")
