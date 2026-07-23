"""Protected parent controls for local child-speech calibration."""

from fastapi import APIRouter, Depends, HTTPException

from gateway.admin.auth import verify_admin
from gateway.app.calibration.schemas import CalibrationStatusResponse
from gateway.app.calibration.service import (
    CalibrationUnavailableError,
    SpeechCalibrationService,
)
from gateway.app.dependencies import get_speech_calibration_service

router = APIRouter(prefix="/api/stt-calibration", tags=["stt calibration"])


@router.get("/status", response_model=CalibrationStatusResponse | None)
async def calibration_status(
    _user: str = Depends(verify_admin),
    service: SpeechCalibrationService = Depends(get_speech_calibration_service),
) -> CalibrationStatusResponse | None:
    try:
        return await service.current()
    except CalibrationUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Calibration is unavailable") from exc


@router.post("/start", response_model=CalibrationStatusResponse)
async def start_calibration(
    _user: str = Depends(verify_admin),
    service: SpeechCalibrationService = Depends(get_speech_calibration_service),
) -> CalibrationStatusResponse:
    try:
        return await service.start()
    except CalibrationUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{session_id}", response_model=CalibrationStatusResponse)
async def cancel_calibration(
    session_id: str,
    _user: str = Depends(verify_admin),
    service: SpeechCalibrationService = Depends(get_speech_calibration_service),
) -> CalibrationStatusResponse:
    try:
        return await service.cancel(session_id)
    except CalibrationUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Calibration is unavailable") from exc
