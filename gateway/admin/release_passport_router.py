"""Authenticated Admin API for actual production release identity."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from gateway.admin.auth import verify_admin
from gateway.admin.monitoring_router import get_monitoring_session
from gateway.admin.release_passport_schemas import ReleasePassportResponse
from gateway.admin.release_passport_service import ReleasePassportService
from gateway.admin.voice_observability_router import get_voice_observability_service
from gateway.admin.voice_observability_service import VoiceObservabilityService
from gateway.app.config import Settings, get_settings

router = APIRouter(prefix="/api/infrastructure/release-passport", tags=["release passport"])


def get_release_passport_service(
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_monitoring_session),
    voice: VoiceObservabilityService = Depends(get_voice_observability_service),
) -> ReleasePassportService:
    return ReleasePassportService(settings, session, voice)


@router.get("", response_model=ReleasePassportResponse)
def get_release_passport(
    response: Response,
    _user: str = Depends(verify_admin),
    service: ReleasePassportService = Depends(get_release_passport_service),
) -> ReleasePassportResponse:
    """Return commits, schema and anonymous Android build identity."""

    response.headers["Cache-Control"] = "no-store"
    return service.get_passport()
