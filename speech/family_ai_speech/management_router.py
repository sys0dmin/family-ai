"""Protected Speech runtime-settings and calibration routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from family_ai_speech.calibration import (
    CalibrationConflictError,
    CalibrationManager,
    CalibrationNotFoundError,
)
from family_ai_speech.http_context import SpeechHttpContext
from family_ai_speech.runtime_settings import (
    RuntimeSettingsApplyError,
    SpeechRuntimeSettingsManager,
)
from family_ai_speech.schemas import (
    CalibrationStartRequest,
    CalibrationStateResponse,
    RuntimeSettingsResponse,
    RuntimeSettingsUpdateRequest,
)

logger = logging.getLogger(__name__)


def build_management_router(context: SpeechHttpContext) -> APIRouter:
    """Build authenticated operator routes independently from public audio API."""

    router = APIRouter(dependencies=[Depends(context.authorize)])
    settings = context.settings

    @router.post(
        "/internal/runtime-settings",
        response_model=RuntimeSettingsResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def update_runtime_settings(
        payload: RuntimeSettingsUpdateRequest,
        manager: SpeechRuntimeSettingsManager = Depends(
            context.runtime_settings_manager
        ),
    ) -> RuntimeSettingsResponse:
        try:
            manager.apply(
                beam_size=payload.stt_beam_size,
                vad_filter=payload.stt_vad_filter,
                max_new_tokens=payload.stt_max_new_tokens,
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
            stt_max_new_tokens=payload.stt_max_new_tokens,
            restart_scheduled=True,
            instance_id=context.instance_id,
        )

    @router.get(
        "/internal/runtime-settings",
        response_model=RuntimeSettingsResponse,
    )
    async def runtime_settings() -> RuntimeSettingsResponse:
        return RuntimeSettingsResponse(
            stt_beam_size=settings.stt_beam_size,
            stt_vad_filter=settings.stt_vad_filter,
            stt_max_new_tokens=settings.stt_max_new_tokens,
            instance_id=context.instance_id,
        )

    @router.post(
        "/internal/calibrations",
        response_model=CalibrationStateResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def start_calibration(
        payload: CalibrationStartRequest,
        manager: CalibrationManager = Depends(context.calibration_manager),
    ) -> CalibrationStateResponse:
        try:
            return manager.start(payload.prompts, payload.initial_prompt)
        except CalibrationConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get(
        "/internal/calibrations/current",
        response_model=CalibrationStateResponse,
    )
    async def current_calibration(
        manager: CalibrationManager = Depends(context.calibration_manager),
    ) -> CalibrationStateResponse:
        try:
            return manager.current()
        except CalibrationNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Calibration not found") from exc

    @router.post(
        "/internal/calibrations/{session_id}/samples/{prompt_id}",
        status_code=204,
    )
    async def add_calibration_sample(
        session_id: str,
        prompt_id: str,
        file: Annotated[UploadFile, File()],
        manager: CalibrationManager = Depends(context.calibration_manager),
    ) -> None:
        content = await file.read(settings.max_audio_bytes + 1)
        if not content:
            raise HTTPException(status_code=400, detail="Empty audio file")
        if len(content) > settings.max_audio_bytes:
            raise HTTPException(status_code=413, detail="Audio file is too large")
        try:
            manager.add_sample(session_id, prompt_id, content)
        except CalibrationNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Calibration not found") from exc
        except CalibrationConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post(
        "/internal/calibrations/{session_id}/complete",
        response_model=CalibrationStateResponse,
    )
    async def complete_calibration(
        session_id: str,
        manager: CalibrationManager = Depends(context.calibration_manager),
    ) -> CalibrationStateResponse:
        try:
            return manager.complete(session_id)
        except CalibrationNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Calibration not found") from exc
        except CalibrationConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.delete(
        "/internal/calibrations/{session_id}",
        response_model=CalibrationStateResponse,
    )
    async def cancel_calibration(
        session_id: str,
        manager: CalibrationManager = Depends(context.calibration_manager),
    ) -> CalibrationStateResponse:
        try:
            return manager.cancel(session_id)
        except CalibrationNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Calibration not found") from exc

    return router
