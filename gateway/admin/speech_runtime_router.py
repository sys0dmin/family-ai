"""Protected Admin controls for local Speech runtime settings."""

from fastapi import APIRouter, Depends, HTTPException, status

from gateway.admin.auth import verify_admin
from gateway.app.dependencies import get_speech_runtime_service
from gateway.app.speech_runtime.schemas import (
    SpeechRuntimeSettings,
    SpeechRuntimeSettingsUpdate,
)
from gateway.app.speech_runtime.service import (
    SpeechRestartTimeoutError,
    SpeechRollbackFailedError,
    SpeechRuntimeService,
    SpeechRuntimeUnavailableError,
)

router = APIRouter(prefix="/api/speech/runtime-settings", tags=["speech runtime"])


@router.get("", response_model=SpeechRuntimeSettings)
async def get_runtime_settings(
    _user: str = Depends(verify_admin),
    service: SpeechRuntimeService = Depends(get_speech_runtime_service),
) -> SpeechRuntimeSettings:
    try:
        return await service.current()
    except SpeechRuntimeUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Speech runtime settings are unavailable",
        ) from exc


@router.put("", response_model=SpeechRuntimeSettings)
async def update_runtime_settings(
    update: SpeechRuntimeSettingsUpdate,
    _user: str = Depends(verify_admin),
    service: SpeechRuntimeService = Depends(get_speech_runtime_service),
) -> SpeechRuntimeSettings:
    try:
        return await service.apply_and_restart(update)
    except SpeechRestartTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Speech did not restart with requested settings",
        ) from exc
    except SpeechRollbackFailedError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Speech settings failed and automatic rollback did not recover",
        ) from exc
    except SpeechRuntimeUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Speech runtime settings could not be applied",
        ) from exc
