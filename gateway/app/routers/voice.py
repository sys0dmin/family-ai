"""HTTP transport for complete voice conversation turns."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response, StreamingResponse

from gateway.app.config import Settings, get_settings
from gateway.app.dependencies import get_voice_service
from gateway.app.observability.voice_metrics import voice_metrics_registry
from gateway.app.routers.speech_response import speech_response
from gateway.app.schemas.voice import SynthesizeTextRequest, VoicePlaybackReport
from gateway.app.services.voice_service import VoiceInputError, VoiceService
from gateway.app.services.voice_streaming import (
    VOICE_STREAM_PROTOCOL,
    voice_stream_registry,
)
from gateway.app.upload_formats import (
    AUDIO_EXTENSIONS,
    normalized_content_type,
    safe_audio_filename,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/voice", tags=["voice"])


async def _read_audio_upload(
    file: UploadFile,
    settings: Settings,
) -> tuple[bytes, str, str]:
    content_type = normalized_content_type(file.content_type)
    if content_type not in AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported audio format",
        )
    content = await file.read(settings.voice_max_audio_bytes + 1)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty audio file",
        )
    if len(content) > settings.voice_max_audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Audio file is too large",
        )
    filename = safe_audio_filename(file.filename, content_type)
    if filename is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported audio format",
        )
    return content, filename, content_type


@router.post("/{conversation_id}/turn", response_class=Response)
async def voice_turn(
    conversation_id: UUID,
    file: UploadFile = File(...),
    recording_duration_ms: int | None = Form(default=None, ge=0, le=3_600_000),
    voice_service: VoiceService = Depends(get_voice_service),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Accept one recording and return the assistant's MP3 response."""

    content, filename, content_type = await _read_audio_upload(file, settings)

    try:
        result = await voice_service.process_voice_turn(
            conversation_id=conversation_id,
            audio_content=content,
            filename=filename,
            content_type=content_type,
            language=settings.voice_language,
            recording_duration_ms=recording_duration_ms,
        )
    except VoiceInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Speech was not recognized",
        ) from exc
    except Exception as exc:
        logger.exception(
            "voice_turn_failed",
            extra={"conversation_id": str(conversation_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Voice provider is temporarily unavailable",
        ) from exc

    return speech_response(result.speech, result.message_id)


@router.post("/{conversation_id}/turn/stream", response_class=StreamingResponse)
async def stream_voice_turn(
    conversation_id: UUID,
    file: UploadFile = File(...),
    recording_duration_ms: int | None = Form(default=None, ge=0, le=3_600_000),
    voice_service: VoiceService = Depends(get_voice_service),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Stream safe assistant speech as independently playable NDJSON parts."""

    content, filename, content_type = await _read_audio_upload(file, settings)
    return StreamingResponse(
        voice_service.stream_voice_turn(
            conversation_id=conversation_id,
            audio_content=content,
            filename=filename,
            content_type=content_type,
            language=settings.voice_language,
            recording_duration_ms=recording_duration_ms,
        ),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "X-Family-AI-Voice-Protocol": VOICE_STREAM_PROTOCOL,
        },
    )


@router.delete("/streams/{turn_id}")
async def cancel_voice_stream(turn_id: UUID) -> dict[str, bool]:
    """Cancel remaining work for a Voice 2.0 turn when the client leaves."""

    return {"cancelled": voice_stream_registry.cancel(turn_id)}


@router.post("/streams/{turn_id}/playback")
async def report_voice_playback(
    turn_id: UUID,
    payload: VoicePlaybackReport,
) -> dict[str, bool]:
    """Record time to the first audio frame actually played on the device."""

    voice_metrics_registry.report_client_playback(
        str(turn_id),
        payload.duration_ms,
    )
    return {"accepted": True}


@router.post("/{conversation_id}/synthesize", response_class=Response)
async def synthesize_text(
    conversation_id: UUID,
    payload: SynthesizeTextRequest,
    voice_service: VoiceService = Depends(get_voice_service),
) -> Response:
    """Speak an existing assistant reply with the conversation agent's voice."""

    try:
        speech = await voice_service.synthesize_text(conversation_id, payload.text)
    except Exception as exc:
        logger.exception(
            "voice_synthesis_failed",
            extra={"conversation_id": str(conversation_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Voice provider is temporarily unavailable",
        ) from exc
    return speech_response(speech)
