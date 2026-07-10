"""Health endpoint for orchestration and deployment checks."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """Public response returned when the Gateway process is ready."""

    status: Literal["ok"]
    service: str


@router.get("/healthz", response_model=HealthResponse, summary="Check Gateway health")
def healthcheck() -> HealthResponse:
    """Return a non-sensitive liveness response."""

    return HealthResponse(status="ok", service="ai-gateway")

