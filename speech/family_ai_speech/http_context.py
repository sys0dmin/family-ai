"""Typed FastAPI dependencies backed by one Speech application instance."""

import secrets
from dataclasses import dataclass
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status

from family_ai_speech.calibration import CalibrationManager
from family_ai_speech.config import SpeechSettings
from family_ai_speech.runtime_settings import SpeechRuntimeSettingsManager
from family_ai_speech.service import LocalSpeechService


@dataclass(frozen=True)
class SpeechHttpContext:
    """Expose runtime state without coupling routers to model initialization."""

    app: FastAPI
    settings: SpeechSettings
    instance_id: str

    def authorize(
        self,
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        expected = self.settings.api_key.get_secret_value()
        if not expected:
            return
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(token, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def service(self) -> LocalSpeechService:
        return self.app.state.speech_service

    def calibration_manager(self) -> CalibrationManager:
        return self.app.state.calibration_manager

    def runtime_settings_manager(self) -> SpeechRuntimeSettingsManager:
        return self.app.state.runtime_settings_manager
