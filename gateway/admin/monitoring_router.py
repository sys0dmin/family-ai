"""Protected infrastructure status API for the Admin UI."""

from collections.abc import Generator

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from gateway.admin.auth import verify_admin
from gateway.admin.monitoring_schemas import InfrastructureStatusResponse
from gateway.admin.monitoring_service import (
    InfrastructureMonitoringService,
    NodeExporterCollector,
)
from gateway.app.config import Settings, get_settings
from gateway.app.db.session import get_session_factory

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


@router.get("", response_model=InfrastructureStatusResponse)
def get_infrastructure_status(
    _user: str = Depends(verify_admin),
    service: InfrastructureMonitoringService = Depends(
        get_infrastructure_monitoring_service
    ),
) -> InfrastructureStatusResponse:
    """Return a current status snapshot without exposing credentials or raw errors."""

    return service.get_status()
