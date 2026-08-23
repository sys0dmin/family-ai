"""Application factory for the local OpenAI-compatible Speech service."""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from family_ai_speech.audio_router import build_audio_router
from family_ai_speech.backends import build_backends
from family_ai_speech.calibration import CalibrationManager
from family_ai_speech.config import SpeechSettings
from family_ai_speech.http_context import SpeechHttpContext
from family_ai_speech.management_router import build_management_router
from family_ai_speech.runtime_settings import SpeechRuntimeSettingsManager
from family_ai_speech.service import LocalSpeechService

logger = logging.getLogger(__name__)


def _install_runtime_state(
    application: FastAPI,
    settings: SpeechSettings,
    speech_service: LocalSpeechService,
    restart_scheduler: Callable[[], None] | None,
) -> CalibrationManager:
    """Install replaceable runtime services in one application-owned state."""

    calibration_manager = CalibrationManager(
        settings.calibration_dir,
        settings.calibration_expiry_hours,
        speech_service,
    )
    application.state.speech_service = speech_service
    application.state.calibration_manager = calibration_manager
    application.state.runtime_settings_manager = SpeechRuntimeSettingsManager(
        settings.runtime_settings_path,
        settings.restart_request_path,
        restart_scheduler,
    )
    return calibration_manager


def create_app(
    settings: SpeechSettings | None = None,
    service: LocalSpeechService | None = None,
    backend_factory: Callable = build_backends,
    restart_scheduler: Callable[[], None] | None = None,
) -> FastAPI:
    """Build the application with injectable model adapters for tests."""

    resolved_settings = settings or SpeechSettings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        speech_service = service
        if speech_service is None:
            stt, tts = await asyncio.to_thread(backend_factory, resolved_settings)
            speech_service = LocalSpeechService(stt, tts)
        calibration_manager = _install_runtime_state(
            application,
            resolved_settings,
            speech_service,
            restart_scheduler,
        )
        calibration_manager.start_housekeeping()
        logger.info(
            "speech_models_loaded",
            extra={
                "stt_model": resolved_settings.stt_model,
                "tts_model": resolved_settings.tts_model,
            },
        )
        try:
            yield
        finally:
            await calibration_manager.close()

    application = FastAPI(
        title="Family AI Speech",
        version="0.1.0",
        lifespan=lifespan,
    )
    if service is not None:
        _install_runtime_state(
            application,
            resolved_settings,
            service,
            restart_scheduler,
        )

    context = SpeechHttpContext(
        app=application,
        settings=resolved_settings,
        instance_id=str(uuid.uuid4()),
    )
    application.include_router(build_audio_router(context))
    application.include_router(build_management_router(context))
    return application


app = create_app()
