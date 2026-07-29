"""Child-safe ephemeral image turns."""

import hashlib
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from gateway.app.dependencies import get_image_understanding_service
from gateway.app.schemas.conversations import MessageResponse
from gateway.app.services.image_understanding_service import (
    ALLOWED_IMAGE_TYPES,
    ImageUnderstandingNotAllowedError,
    ImageUnderstandingService,
    ImageUnderstandingUnavailableError,
    InvalidImageError,
)

router = APIRouter(prefix="/v1/vision", tags=["vision"])
logger = logging.getLogger(__name__)


@router.post(
    "/{conversation_id}/turn",
    response_model=MessageResponse,
    summary="Process one ephemeral child image and question",
)
async def process_image_turn(
    conversation_id: uuid.UUID,
    file: UploadFile = File(...),
    question: str = Form(
        default="Алиса, расскажи, что интересного видно на этой фотографии?",
        min_length=1,
        max_length=8000,
    ),
    service: ImageUnderstandingService = Depends(get_image_understanding_service),
) -> MessageResponse:
    content_type = (file.content_type or "").split(";", maxsplit=1)[0].lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only JPEG, PNG and WebP images are supported",
        )
    content = await file.read(service.max_image_bytes + 1)
    if len(content) > service.max_image_bytes:
        logger.info(
            "vision_image_rejected_too_large",
            extra={
                "conversation_id": str(conversation_id),
                "content_type": content_type,
                "bytes_read": len(content),
                "max_bytes": service.max_image_bytes,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Image is too large",
        )
    normalized_question = question.strip()
    if not normalized_question:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Question must not be blank",
        )
    logger.info(
        "vision_image_received",
        extra={
            "conversation_id": str(conversation_id),
            "content_type": content_type,
            "image_bytes": len(content),
            "image_sha256_prefix": hashlib.sha256(content).hexdigest()[:16],
        },
    )
    try:
        message = await service.process_turn(
            conversation_id,
            question=normalized_question,
            image_content=content,
            content_type=content_type,
        )
    except ImageUnderstandingNotAllowedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This agent cannot inspect images",
        ) from exc
    except InvalidImageError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded image is invalid",
        ) from exc
    except ImageUnderstandingUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image understanding is unavailable",
        ) from exc
    finally:
        await file.close()
    return MessageResponse.model_validate(message)
