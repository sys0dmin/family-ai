"""HTTP transport for complete voice conversation turns."""

import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response

from gateway.app.config import Settings, get_settings
from gateway.app.dependencies import get_voice_service
from gateway.app.services.voice_service import VoiceInputError, VoiceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/voice", tags=["voice"])

SUPPORTED_AUDIO_TYPES = {
    "audio/m4a": "m4a",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/webm": "webm",
    "video/webm": "webm",
}


@router.post("/{conversation_id}/turn", response_class=Response)
async def voice_turn(
    conversation_id: UUID,
    file: UploadFile = File(...),
    voice_service: VoiceService = Depends(get_voice_service),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Accept one recording and return the assistant's MP3 response."""

    content_type = (file.content_type or "").split(";", maxsplit=1)[0].lower()
    extension = SUPPORTED_AUDIO_TYPES.get(content_type)
    if extension is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported audio format",
        )

    content = await file.read(settings.voice_max_audio_bytes + 1)
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty audio file")
    if len(content) > settings.voice_max_audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Audio file is too large",
        )

    original_stem = Path(file.filename or "recording").stem[:80] or "recording"
    filename = f"{original_stem}.{extension}"

    try:
        speech = await voice_service.process_voice_turn(
            conversation_id=conversation_id,
            audio_content=content,
            filename=filename,
            content_type=content_type,
            language=settings.voice_language,
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

    return Response(
        content=speech.audio_content,
        media_type=speech.content_type,
        headers={"Cache-Control": "no-store"},
    )
