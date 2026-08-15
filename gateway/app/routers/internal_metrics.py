"""Loopback-only runtime observability endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from gateway.app.config import Settings, get_settings
from gateway.app.observability.runtime_identity import runtime_identity
from gateway.app.observability.voice_metrics import voice_metrics_registry
from gateway.app.safety.metrics import safety_metrics_registry
from gateway.app.safety.reporting import policy_snapshot, scenario_report
from gateway.app.services.voice_execution import voice_admission_controller

router = APIRouter(prefix="/internal", include_in_schema=False)


def _require_loopback(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


@router.get("/voice-metrics")
async def voice_metrics(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Expose anonymized voice timings to the colocated admin service."""

    _require_loopback(request)
    snapshot = voice_metrics_registry.snapshot()
    snapshot["admission"] = voice_admission_controller.snapshot(
        max_in_flight=settings.voice_max_in_flight
    )
    return snapshot


@router.get("/runtime-identity")
async def get_runtime_identity(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Expose release identity only to the colocated Admin process."""

    _require_loopback(request)
    return runtime_identity(settings)


@router.get("/safety-policy")
async def safety_policy(request: Request) -> dict[str, object]:
    _require_loopback(request)
    return policy_snapshot()


@router.post("/safety-policy/scenarios")
async def run_safety_scenarios(request: Request) -> dict[str, object]:
    _require_loopback(request)
    return scenario_report()


@router.delete("/safety-policy/metrics")
async def reset_safety_metrics(request: Request) -> dict[str, object]:
    _require_loopback(request)
    safety_metrics_registry.reset()
    return policy_snapshot()
