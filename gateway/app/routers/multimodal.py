"""HTTP transport for one spoken question about one ephemeral image."""

import hashlib
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response

from gateway.app.config import Settings, get_settings
from gateway.app.dependencies import get_multimodal_turn_service
from gateway.app.routers.speech_response import speech_response
from gateway.app.services.image_understanding_service import (
    ALLOWED_IMAGE_TYPES,
    ImageUnderstandingNotAllowedError,
    ImageUnderstandingUnavailableError,
    InvalidImageError,
)
from gateway.app.services.multimodal_turn_service import MultimodalTurnService
from gateway.app.services.voice_service import VoiceInputError
from gateway.app.upload_formats import (
    AUDIO_EXTENSIONS,
    normalized_content_type,
    safe_audio_filename,
)

router = APIRouter(prefix="/v1/multimodal", tags=["multimodal"])
logger = logging.getLogger(__name__)


@router.post("/{conversation_id}/turn", response_class=Response)
async def multimodal_turn(
    conversation_id: UUID,
    image: UploadFile = File(...),
    audio: UploadFile = File(...),
    recording_duration_ms: int | None = Form(default=None, ge=0, le=3_600_000),
    service: MultimodalTurnService = Depends(get_multimodal_turn_service),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Accept one image and one spoken question; return the safe spoken answer."""

    try:
        image_type = normalized_content_type(image.content_type)
        if image_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported image format",
            )
        audio_type = normalized_content_type(audio.content_type)
        if audio_type not in AUDIO_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported audio format",
            )
        audio_filename = safe_audio_filename(audio.filename, audio_type)
        if audio_filename is None:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported audio format",
            )

        image_content = await image.read(settings.vision_max_image_bytes + 1)
        if not image_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty image file",
            )
        if len(image_content) > settings.vision_max_image_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Image file is too large",
            )
        audio_content = await audio.read(settings.voice_max_audio_bytes + 1)
        if not audio_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty audio file",
            )
        if len(audio_content) > settings.voice_max_audio_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Audio file is too large",
            )

        logger.info(
            "multimodal_upload_received",
            extra={
                "conversation_id": str(conversation_id),
                "image_content_type": image_type,
                "image_bytes": len(image_content),
                "image_sha256_prefix": hashlib.sha256(image_content).hexdigest()[:16],
                "audio_content_type": audio_type,
                "audio_bytes": len(audio_content),
                "recording_duration_ms": recording_duration_ms,
            },
        )
        try:
            result = await service.process_turn(
                conversation_id,
                image_content=image_content,
                image_content_type=image_type,
                audio_content=audio_content,
                audio_filename=audio_filename,
                audio_content_type=audio_type,
                language=settings.voice_language,
                recording_duration_ms=recording_duration_ms,
            )
        except ImageUnderstandingNotAllowedError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This agent cannot inspect images",
            ) from exc
        except InvalidImageError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="The uploaded image is invalid",
            ) from exc
        except VoiceInputError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Speech was not recognized",
            ) from exc
        except ImageUnderstandingUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Image understanding is unavailable",
            ) from exc
        except Exception as exc:
            logger.exception(
                "multimodal_turn_failed",
                extra={"conversation_id": str(conversation_id)},
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Multimodal providers are temporarily unavailable",
            ) from exc

        return speech_response(result.speech, result.message_id)
    finally:
        await image.close()
        await audio.close()
