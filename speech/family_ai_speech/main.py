"""OpenAI-compatible HTTP API for local STT and TTS."""

import asyncio
import logging
import secrets
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from family_ai_speech.backends import build_backends
from family_ai_speech.calibration import (
    CalibrationConflictError,
    CalibrationManager,
    CalibrationNotFoundError,
)
from family_ai_speech.config import SpeechSettings
from family_ai_speech.runtime_settings import (
    RuntimeSettingsApplyError,
    SpeechRuntimeSettingsManager,
)
from family_ai_speech.schemas import (
    CalibrationStartRequest,
    CalibrationStateResponse,
    RuntimeSettingsResponse,
    RuntimeSettingsUpdateRequest,
    SpeechRuntimeMetricsResponse,
    SynthesisRequest,
    TranscriptionSegmentResponse,
    TranscriptionVerboseResponse,
)
from family_ai_speech.service import LocalSpeechService

logger = logging.getLogger(__name__)

SUPPORTED_AUDIO_TYPES = frozenset(
    {
        "audio/flac",
        "audio/mp4",
        "audio/mpeg",
        "audio/ogg",
        "audio/wav",
        "audio/webm",
        "audio/x-m4a",
        "audio/x-wav",
    }
)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_app(
    settings: SpeechSettings | None = None,
    service: LocalSpeechService | None = None,
    backend_factory: Callable = build_backends,
    restart_scheduler: Callable[[], None] | None = None,
) -> FastAPI:
    """Build the application with injectable model adapters for tests."""

    resolved_settings = settings or SpeechSettings()
    instance_id = str(uuid.uuid4())

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if service is not None:
            application.state.speech_service = service
        else:
            stt, tts = await asyncio.to_thread(backend_factory, resolved_settings)
            application.state.speech_service = LocalSpeechService(stt, tts)
        application.state.calibration_manager = CalibrationManager(
            resolved_settings.calibration_dir,
            resolved_settings.calibration_expiry_hours,
            application.state.speech_service,
        )
        application.state.runtime_settings_manager = SpeechRuntimeSettingsManager(
            resolved_settings.runtime_settings_path,
            resolved_settings.restart_request_path,
            restart_scheduler,
        )
        application.state.calibration_manager.start_housekeeping()
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
            await application.state.calibration_manager.close()

    app = FastAPI(
        title="Family AI Speech",
        version="0.1.0",
        lifespan=lifespan,
    )
    if service is not None:
        app.state.speech_service = service
        app.state.calibration_manager = CalibrationManager(
            resolved_settings.calibration_dir,
            resolved_settings.calibration_expiry_hours,
            service,
        )
        app.state.runtime_settings_manager = SpeechRuntimeSettingsManager(
            resolved_settings.runtime_settings_path,
            resolved_settings.restart_request_path,
            restart_scheduler,
        )

    def authorize(
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        expected = resolved_settings.api_key.get_secret_value()
        if not expected:
            return
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(token, expected):
            raise _unauthorized()

    def get_service() -> LocalSpeechService:
        return app.state.speech_service

    def get_calibration_manager() -> CalibrationManager:
        return app.state.calibration_manager

    def get_runtime_settings_manager() -> SpeechRuntimeSettingsManager:
        return app.state.runtime_settings_manager

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "family-ai-speech",
            "stt_model": resolved_settings.stt_model,
            "tts_model": resolved_settings.tts_model,
        }

    @app.get(
        "/internal/metrics",
        response_model=SpeechRuntimeMetricsResponse,
        dependencies=[Depends(authorize)],
    )
    async def runtime_metrics(
        speech_service: LocalSpeechService = Depends(get_service),
    ) -> SpeechRuntimeMetricsResponse:
        return speech_service.metrics_snapshot()

    @app.post(
        "/v1/audio/transcriptions",
        dependencies=[Depends(authorize)],
    )
    async def transcribe(
        file: Annotated[UploadFile, File()],
        model: Annotated[str, Form()],
        language: Annotated[str, Form()] = "ru",
        response_format: Annotated[str, Form()] = "text",
        temperature: Annotated[float, Form()] = 0.0,
        prompt: Annotated[str | None, Form()] = None,
        speech_service: LocalSpeechService = Depends(get_service),
        x_request_id: uuid.UUID | None = Header(default=None, alias="X-Request-ID"),
    ) -> Response:
        del temperature
        if model != resolved_settings.stt_model:
            raise HTTPException(status_code=400, detail="Unsupported transcription model")
        if response_format not in {"text", "verbose_json"}:
            raise HTTPException(status_code=400, detail="Unsupported transcription response format")
        if (file.content_type or "").lower() not in SUPPORTED_AUDIO_TYPES:
            raise HTTPException(status_code=415, detail="Unsupported audio format")

        content = await file.read(resolved_settings.max_audio_bytes + 1)
        if not content:
            raise HTTPException(status_code=400, detail="Empty audio file")
        if len(content) > resolved_settings.max_audio_bytes:
            raise HTTPException(status_code=413, detail="Audio file is too large")

        try:
            result = await speech_service.transcribe(content, language, prompt)
        except Exception as exc:
            logger.exception(
                "local_transcription_failed",
                extra={"request_id": str(x_request_id) if x_request_id else None},
            )
            raise HTTPException(status_code=502, detail="Local transcription failed") from exc
        if response_format == "text":
            return PlainTextResponse(
                result.text,
                headers={"X-Request-ID": str(x_request_id)} if x_request_id else None,
            )
        verbose_response = TranscriptionVerboseResponse(
            language=result.language,
            duration=result.duration_seconds,
            text=result.text,
            segments=[
                TranscriptionSegmentResponse(
                    id=segment.id,
                    start=segment.start,
                    end=segment.end,
                    text=segment.text,
                    avg_logprob=segment.avg_logprob,
                    no_speech_prob=segment.no_speech_probability,
                )
                for segment in result.segments
            ],
        )
        return JSONResponse(
            verbose_response.model_dump(),
            headers={"X-Request-ID": str(x_request_id)} if x_request_id else None,
        )

    @app.post(
        "/v1/audio/speech",
        response_class=Response,
        dependencies=[Depends(authorize)],
    )
    async def synthesize(
        payload: SynthesisRequest,
        speech_service: LocalSpeechService = Depends(get_service),
        x_request_id: uuid.UUID | None = Header(default=None, alias="X-Request-ID"),
    ) -> Response:
        if payload.model != resolved_settings.tts_model:
            raise HTTPException(status_code=400, detail="Unsupported speech model")
        text = payload.input.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Speech input is empty")
        if len(text) > resolved_settings.max_text_characters:
            raise HTTPException(status_code=413, detail="Speech input is too long")

        try:
            audio = await speech_service.synthesize(text, payload.voice)
        except Exception as exc:
            logger.exception(
                "local_synthesis_failed",
                extra={"request_id": str(x_request_id) if x_request_id else None},
            )
            raise HTTPException(status_code=502, detail="Local synthesis failed") from exc
        return Response(
            content=audio,
            media_type="audio/wav",
            headers={
                "Content-Disposition": 'inline; filename="speech.wav"',
                **({"X-Request-ID": str(x_request_id)} if x_request_id else {}),
            },
        )

    @app.post(
        "/internal/runtime-settings",
        response_model=RuntimeSettingsResponse,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(authorize)],
    )
    async def update_runtime_settings(
        payload: RuntimeSettingsUpdateRequest,
        manager: SpeechRuntimeSettingsManager = Depends(get_runtime_settings_manager),
    ) -> RuntimeSettingsResponse:
        try:
            manager.apply(
                beam_size=payload.stt_beam_size,
                vad_filter=payload.stt_vad_filter,
            )
        except (OSError, RuntimeSettingsApplyError) as exc:
            logger.exception("speech_runtime_settings_apply_failed")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Speech runtime settings could not be applied",
            ) from exc
        return RuntimeSettingsResponse(
            stt_beam_size=payload.stt_beam_size,
            stt_vad_filter=payload.stt_vad_filter,
            restart_scheduled=True,
            instance_id=instance_id,
        )

    @app.get(
        "/internal/runtime-settings",
        response_model=RuntimeSettingsResponse,
        dependencies=[Depends(authorize)],
    )
    async def runtime_settings() -> RuntimeSettingsResponse:
        return RuntimeSettingsResponse(
            stt_beam_size=resolved_settings.stt_beam_size,
            stt_vad_filter=resolved_settings.stt_vad_filter,
            instance_id=instance_id,
        )

    @app.post(
        "/internal/calibrations",
        response_model=CalibrationStateResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(authorize)],
    )
    async def start_calibration(
        payload: CalibrationStartRequest,
        manager: CalibrationManager = Depends(get_calibration_manager),
    ) -> CalibrationStateResponse:
        try:
            return manager.start(payload.prompts, payload.initial_prompt)
        except CalibrationConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get(
        "/internal/calibrations/current",
        response_model=CalibrationStateResponse,
        dependencies=[Depends(authorize)],
    )
    async def current_calibration(
        manager: CalibrationManager = Depends(get_calibration_manager),
    ) -> CalibrationStateResponse:
        try:
            return manager.current()
        except CalibrationNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Calibration not found") from exc

    @app.post(
        "/internal/calibrations/{session_id}/samples/{prompt_id}",
        status_code=204,
        dependencies=[Depends(authorize)],
    )
    async def add_calibration_sample(
        session_id: str,
        prompt_id: str,
        file: Annotated[UploadFile, File()],
        manager: CalibrationManager = Depends(get_calibration_manager),
    ) -> None:
        content = await file.read(resolved_settings.max_audio_bytes + 1)
        if not content:
            raise HTTPException(status_code=400, detail="Empty audio file")
        if len(content) > resolved_settings.max_audio_bytes:
            raise HTTPException(status_code=413, detail="Audio file is too large")
        try:
            manager.add_sample(session_id, prompt_id, content)
        except CalibrationNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Calibration not found") from exc
        except CalibrationConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/internal/calibrations/{session_id}/complete",
        response_model=CalibrationStateResponse,
        dependencies=[Depends(authorize)],
    )
    async def complete_calibration(
        session_id: str,
        manager: CalibrationManager = Depends(get_calibration_manager),
    ) -> CalibrationStateResponse:
        try:
            return manager.complete(session_id)
        except CalibrationNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Calibration not found") from exc
        except CalibrationConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.delete(
        "/internal/calibrations/{session_id}",
        response_model=CalibrationStateResponse,
        dependencies=[Depends(authorize)],
    )
    async def cancel_calibration(
        session_id: str,
        manager: CalibrationManager = Depends(get_calibration_manager),
    ) -> CalibrationStateResponse:
        try:
            return manager.cancel(session_id)
        except CalibrationNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Calibration not found") from exc

    return app


app = create_app()
