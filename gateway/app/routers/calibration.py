"""Child-facing transport for an explicitly armed STT calibration session."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response

from gateway.app.calibration.prompts import CALIBRATION_PROMPTS
from gateway.app.calibration.schemas import CalibrationDiscoveryResponse
from gateway.app.calibration.service import (
    CalibrationUnavailableError,
    SpeechCalibrationService,
)
from gateway.app.config import Settings, get_settings
from gateway.app.dependencies import get_ai_provider, get_speech_calibration_service
from gateway.app.providers.base import AIProvider
from gateway.app.providers.schemas import SpeechRequest

router = APIRouter(prefix="/v1/stt-calibration", tags=["stt calibration"])


@router.get("/active", response_model=CalibrationDiscoveryResponse)
async def active_calibration(
    service: SpeechCalibrationService = Depends(get_speech_calibration_service),
) -> CalibrationDiscoveryResponse:
    try:
        current = await service.current()
    except CalibrationUnavailableError:
        return CalibrationDiscoveryResponse(active=False)
    if current is None or current.status != "collecting":
        return CalibrationDiscoveryResponse(active=False)
    return CalibrationDiscoveryResponse(
        active=True,
        session_id=current.id,
        prompts=[
            {
                "id": prompt.id,
                "kind": prompt.kind,
                "phrase": prompt.expected_text,
                "icon": prompt.icon,
            }
            for prompt in CALIBRATION_PROMPTS
        ],
        collected_prompt_ids=current.collected_prompt_ids,
    )


@router.get("/{session_id}/prompts/{prompt_id}/audio", response_class=Response)
async def calibration_prompt_audio(
    session_id: str,
    prompt_id: str,
    provider: AIProvider = Depends(get_ai_provider),
    service: SpeechCalibrationService = Depends(get_speech_calibration_service),
    settings: Settings = Depends(get_settings),
) -> Response:
    prompt = next((item for item in CALIBRATION_PROMPTS if item.id == prompt_id), None)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Calibration prompt not found")
    current = await _require_collecting_session(service, session_id)
    del current
    speech = await provider.synthesize_speech(
        SpeechRequest(text=prompt.spoken_instruction, voice=settings.calibration_voice)
    )
    return Response(
        content=speech.audio_content,
        media_type=speech.content_type,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/{session_id}/samples/{prompt_id}", status_code=204)
async def upload_calibration_sample(
    session_id: str,
    prompt_id: str,
    file: Annotated[UploadFile, File()],
    service: SpeechCalibrationService = Depends(get_speech_calibration_service),
    settings: Settings = Depends(get_settings),
) -> None:
    if not any(prompt.id == prompt_id for prompt in CALIBRATION_PROMPTS):
        raise HTTPException(status_code=404, detail="Calibration prompt not found")
    await _require_collecting_session(service, session_id)
    content_type = (file.content_type or "").split(";", maxsplit=1)[0].lower()
    if content_type not in {"audio/wav", "audio/x-wav"}:
        raise HTTPException(status_code=415, detail="Calibration requires WAV audio")
    audio = await file.read(settings.voice_max_audio_bytes + 1)
    if not audio:
        raise HTTPException(status_code=400, detail="Empty audio file")
    if len(audio) > settings.voice_max_audio_bytes:
        raise HTTPException(status_code=413, detail="Audio file is too large")
    try:
        await service.add_sample(session_id, prompt_id, audio, content_type)
    except CalibrationUnavailableError as exc:
        raise HTTPException(status_code=502, detail="Calibration upload failed") from exc


@router.post("/{session_id}/complete", status_code=202)
async def complete_calibration(
    session_id: str,
    service: SpeechCalibrationService = Depends(get_speech_calibration_service),
) -> dict[str, str]:
    await _require_collecting_session(service, session_id)
    try:
        await service.complete(session_id)
    except CalibrationUnavailableError as exc:
        raise HTTPException(status_code=502, detail="Calibration could not start") from exc
    return {"status": "running"}


async def _require_collecting_session(
    service: SpeechCalibrationService,
    session_id: str,
):
    try:
        current = await service.current()
    except CalibrationUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Calibration is unavailable") from exc
    if current is None or current.id != session_id or current.status != "collecting":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Calibration session is not collecting",
        )
    return current
