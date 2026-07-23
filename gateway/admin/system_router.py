"""Authenticated operational actions for the Family AI Gateway."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from gateway.admin.auth import verify_admin
from gateway.admin.system_service import GatewayRestartError, GatewaySystemService

router = APIRouter(prefix="/api/system", tags=["system administration"])


class GatewayRestartResponse(BaseModel):
    status: str
    service: str
    active: bool


def get_gateway_system_service() -> GatewaySystemService:
    return GatewaySystemService()


@router.post("/gateway/restart", response_model=GatewayRestartResponse)
def restart_gateway(
    _user: str = Depends(verify_admin),
    service: GatewaySystemService = Depends(get_gateway_system_service),
) -> GatewayRestartResponse:
    try:
        result = service.restart_gateway()
    except GatewayRestartError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gateway service could not be restarted",
        ) from exc
    return GatewayRestartResponse(
        status="restarted",
        service=result.service,
        active=result.active,
    )
