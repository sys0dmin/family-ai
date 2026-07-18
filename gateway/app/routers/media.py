"""Safe local transport for externally hosted message media."""

import logging
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from gateway.app.dependencies import get_visual_media_service
from gateway.app.services.visual_media_service import VisualMediaService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/media", tags=["media"])


@router.get("/{media_id}/content", response_class=Response)
async def get_media_content(
    media_id: UUID,
    service: VisualMediaService = Depends(get_visual_media_service),
) -> Response:
    """Proxy one validated image while keeping the child browser on the home Gateway."""

    try:
        image = await service.fetch_image(media_id)
    except httpx.HTTPError as exc:
        logger.warning("media_proxy_failed", extra={"media_id": str(media_id)})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Image source is temporarily unavailable",
        ) from exc
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image unavailable")
    return Response(
        content=image.content,
        media_type=image.content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )
