"""Protected voice observability endpoint."""

from fastapi import APIRouter, Depends

from gateway.admin.auth import verify_admin
from gateway.admin.voice_observability_schemas import VoiceObservabilityResponse
from gateway.admin.voice_observability_service import VoiceObservabilityService
from gateway.app.config import Settings, get_settings

router = APIRouter(prefix="/api/voice-observability", tags=["voice observability"])


def get_voice_observability_service(
    settings: Settings = Depends(get_settings),
) -> VoiceObservabilityService:
    return VoiceObservabilityService(settings)


@router.get("", response_model=VoiceObservabilityResponse)
def get_voice_observability(
    _user: str = Depends(verify_admin),
    service: VoiceObservabilityService = Depends(get_voice_observability_service),
) -> VoiceObservabilityResponse:
    return service.get_snapshot()
