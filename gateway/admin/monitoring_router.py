"""Protected infrastructure status API for the Admin UI."""

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from gateway.admin.auth import verify_admin
from gateway.admin.monitoring_schemas import InfrastructureStatusResponse
from gateway.admin.monitoring_service import (
    InfrastructureMonitoringService,
    NodeExporterCollector,
)
from gateway.admin.operational_alert_schemas import (
    OperationalAlertCollection,
    OperationalAlertResponse,
    OperationalOverviewResponse,
)
from gateway.admin.operational_alert_service import OperationalAlertService
from gateway.admin.voice_observability_router import get_voice_observability_service
from gateway.admin.voice_observability_service import VoiceObservabilityService
from gateway.app.config import Settings, get_settings
from gateway.app.db.session import get_db_session, get_session_factory

router = APIRouter(prefix="/api/infrastructure", tags=["infrastructure monitoring"])
_node_collector = NodeExporterCollector()


def get_monitoring_session() -> Generator[Session]:
    """Yield a read-only database session for health inspection."""

    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def get_infrastructure_monitoring_service(
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_monitoring_session),
) -> InfrastructureMonitoringService:
    return InfrastructureMonitoringService(
        settings=settings,
        session=session,
        node_collector=_node_collector,
    )


def get_operational_alert_service(
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db_session),
) -> OperationalAlertService:
    return OperationalAlertService(session, settings)


@router.get("", response_model=InfrastructureStatusResponse)
def get_infrastructure_status(
    _user: str = Depends(verify_admin),
    service: InfrastructureMonitoringService = Depends(get_infrastructure_monitoring_service),
) -> InfrastructureStatusResponse:
    """Return a current status snapshot without exposing credentials or raw errors."""

    return service.get_status()


@router.post("/scan", response_model=OperationalOverviewResponse)
def scan_operational_status(
    _user: str = Depends(verify_admin),
    monitoring: InfrastructureMonitoringService = Depends(get_infrastructure_monitoring_service),
    voice: VoiceObservabilityService = Depends(get_voice_observability_service),
    alerts: OperationalAlertService = Depends(get_operational_alert_service),
) -> OperationalOverviewResponse:
    """Collect one local snapshot and reconcile privacy-safe technical episodes."""

    infrastructure_snapshot = monitoring.get_status()
    voice_snapshot = voice.get_snapshot()
    return OperationalOverviewResponse(
        infrastructure=infrastructure_snapshot,
        voice=voice_snapshot,
        alerts=alerts.reconcile(infrastructure_snapshot, voice_snapshot),
    )


@router.get("/alerts", response_model=OperationalAlertCollection)
def get_operational_alerts(
    _user: str = Depends(verify_admin),
    alerts: OperationalAlertService = Depends(get_operational_alert_service),
) -> OperationalAlertCollection:
    """Return active and recently resolved technical episodes without rescanning."""

    return alerts.list_alerts()


@router.post(
    "/alerts/{alert_id}/acknowledge",
    response_model=OperationalAlertResponse,
)
def acknowledge_operational_alert(
    alert_id: str,
    user: str = Depends(verify_admin),
    alerts: OperationalAlertService = Depends(get_operational_alert_service),
) -> OperationalAlertResponse:
    """Record that the parent saw one still-active technical alert."""

    try:
        from uuid import UUID

        parsed_id = UUID(alert_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found"
        ) from exc
    result = alerts.acknowledge(parsed_id, user)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return result
