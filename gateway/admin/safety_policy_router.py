"""Protected Safety Policy catalog, metrics and scenario controls."""

from fastapi import APIRouter, Depends, HTTPException, status

from gateway.admin.auth import verify_admin
from gateway.admin.safety_policy_schemas import (
    SafetyPolicySnapshot,
    SafetyScenarioReport,
)
from gateway.admin.safety_policy_service import (
    SafetyPolicyAdminError,
    SafetyPolicyAdminService,
)
from gateway.app.config import Settings, get_settings

router = APIRouter(prefix="/api/safety-policy", tags=["safety policy"])


def get_safety_policy_admin_service(
    settings: Settings = Depends(get_settings),
) -> SafetyPolicyAdminService:
    return SafetyPolicyAdminService(settings)


@router.get("", response_model=SafetyPolicySnapshot)
def get_policy_snapshot(
    _user: str = Depends(verify_admin),
    service: SafetyPolicyAdminService = Depends(get_safety_policy_admin_service),
) -> SafetyPolicySnapshot:
    try:
        return service.snapshot()
    except SafetyPolicyAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Safety Policy runtime is unavailable",
        ) from exc


@router.delete("/metrics", response_model=SafetyPolicySnapshot)
def reset_policy_metrics(
    _user: str = Depends(verify_admin),
    service: SafetyPolicyAdminService = Depends(get_safety_policy_admin_service),
) -> SafetyPolicySnapshot:
    try:
        return service.reset_metrics()
    except SafetyPolicyAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Safety Policy metrics could not be reset",
        ) from exc


@router.post("/scenarios", response_model=SafetyScenarioReport)
def run_policy_scenarios(
    _user: str = Depends(verify_admin),
    service: SafetyPolicyAdminService = Depends(get_safety_policy_admin_service),
) -> SafetyScenarioReport:
    try:
        return service.run_scenarios()
    except SafetyPolicyAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Safety Policy scenarios could not run",
        ) from exc
