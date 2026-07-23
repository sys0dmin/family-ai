"""Loopback-only runtime observability endpoints."""

from fastapi import APIRouter, HTTPException, Request, status

from gateway.app.observability.voice_metrics import voice_metrics_registry

router = APIRouter(prefix="/internal", include_in_schema=False)


@router.get("/voice-metrics")
async def voice_metrics(request: Request) -> dict[str, object]:
    """Expose anonymized voice timings to the colocated admin service."""

    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return voice_metrics_registry.snapshot()
