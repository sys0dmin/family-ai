"""Server-side adapter for persistent Speech runtime settings."""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlsplit, urlunsplit

import httpx

from gateway.app.config import Settings
from gateway.app.speech_runtime.schemas import (
    SpeechRuntimeSettings,
    SpeechRuntimeSettingsUpdate,
)


class SpeechRuntimeUnavailableError(RuntimeError):
    """Raised when the private Speech control API cannot be reached."""


class SpeechRestartTimeoutError(RuntimeError):
    """Raised when the restarted process does not report requested settings."""


class SpeechRollbackFailedError(RuntimeError):
    """Raised when requested settings failed and previous values could not recover."""


class SpeechRuntimeService:
    """Apply approved settings and verify them in a newly started process."""

    def __init__(self, settings: Settings) -> None:
        self._base_url = self._resolve_base_url(settings.speech_base_url)
        self._token = settings.speech_api_key.get_secret_value()
        self._request_timeout = settings.calibration_request_timeout_seconds
        self._restart_timeout = settings.speech_restart_timeout_seconds

    async def current(self) -> SpeechRuntimeSettings:
        return await self._request("GET")

    async def apply_and_restart(
        self,
        update: SpeechRuntimeSettingsUpdate,
    ) -> SpeechRuntimeSettings:
        previous = await self.current()
        await self._request("POST", json=update.model_dump())
        try:
            return await self._wait_for_settings(
                previous_instance_id=previous.instance_id,
                expected=update,
            )
        except SpeechRestartTimeoutError as exc:
            await self._restore_previous(previous)
            raise SpeechRestartTimeoutError(
                "Speech restart verification timed out; previous settings were restored"
            ) from exc

    async def _restore_previous(self, previous: SpeechRuntimeSettings) -> None:
        rollback = SpeechRuntimeSettingsUpdate(
            stt_beam_size=previous.stt_beam_size,
            stt_vad_filter=previous.stt_vad_filter,
            stt_max_new_tokens=previous.stt_max_new_tokens,
        )
        try:
            current = await self.current()
            await self._request("POST", json=rollback.model_dump())
            await self._wait_for_settings(
                previous_instance_id=current.instance_id,
                expected=rollback,
            )
        except (SpeechRestartTimeoutError, SpeechRuntimeUnavailableError) as exc:
            raise SpeechRollbackFailedError(
                "Speech previous runtime settings could not be restored"
            ) from exc

    async def _wait_for_settings(
        self,
        *,
        previous_instance_id: str,
        expected: SpeechRuntimeSettingsUpdate,
    ) -> SpeechRuntimeSettings:
        deadline = time.monotonic() + self._restart_timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(1)
            try:
                current = await self.current()
            except SpeechRuntimeUnavailableError:
                continue
            if (
                current.instance_id != previous_instance_id
                and current.stt_beam_size == expected.stt_beam_size
                and current.stt_vad_filter is expected.stt_vad_filter
                and current.stt_max_new_tokens == expected.stt_max_new_tokens
            ):
                return current
        raise SpeechRestartTimeoutError("Speech restart verification timed out")

    async def _request(self, method: str, **kwargs) -> SpeechRuntimeSettings:
        if self._base_url is None:
            raise SpeechRuntimeUnavailableError("Local Speech Service is not configured")
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            async with httpx.AsyncClient(timeout=self._request_timeout) as client:
                response = await client.request(
                    method,
                    self._base_url + "/internal/runtime-settings",
                    headers=headers,
                    **kwargs,
                )
        except httpx.HTTPError as exc:
            raise SpeechRuntimeUnavailableError(
                "Speech runtime control is unavailable"
            ) from exc
        if response.status_code >= 400:
            raise SpeechRuntimeUnavailableError(
                f"Speech runtime control returned HTTP {response.status_code}"
            )
        return SpeechRuntimeSettings.model_validate(response.json())

    @staticmethod
    def _resolve_base_url(speech_base_url: str | None) -> str | None:
        if not speech_base_url:
            return None
        parsed = urlsplit(speech_base_url)
        return urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")
