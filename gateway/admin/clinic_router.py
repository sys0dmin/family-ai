"""Protected pretend-clinic catalog preview and session controls."""

import uuid
from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from gateway.admin.auth import verify_admin
from gateway.admin.clinic_schemas import (
    ClinicAdminCatalogResponse,
    ClinicAdminSessionsResponse,
)
from gateway.app.clinic import ClinicCaseCatalog, ClinicConversationError, ClinicGameService
from gateway.app.config import get_settings
from gateway.app.db.session import get_session_factory
from gateway.app.routers.clinic import serialize_clinic_session
from gateway.app.schemas.clinic import ClinicSessionResponse

router = APIRouter(prefix="/api/clinic", tags=["clinic administration"])


def get_clinic_admin_session() -> Generator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_clinic_admin_service(
    session: Session = Depends(get_clinic_admin_session),
) -> ClinicGameService:
    settings = get_settings()
    return ClinicGameService(
        session,
        ClinicCaseCatalog(),
        retention_hours=settings.activity_retention_hours,
    )


@router.get("/catalog", response_model=ClinicAdminCatalogResponse)
def clinic_catalog(
    _parent: str = Depends(verify_admin),
    service: ClinicGameService = Depends(get_clinic_admin_service),
) -> ClinicAdminCatalogResponse:
    return ClinicAdminCatalogResponse(
        schema_version=service.catalog.schema_version,
        items=list(service.catalog.list()),
    )


@router.get("/sessions", response_model=ClinicAdminSessionsResponse)
def clinic_sessions(
    _parent: str = Depends(verify_admin),
    service: ClinicGameService = Depends(get_clinic_admin_service),
) -> ClinicAdminSessionsResponse:
    service.purge_expired()
    return ClinicAdminSessionsResponse(
        items=[serialize_clinic_session(service, item) for item in service.list_sessions()]
    )


@router.post(
    "/sessions/{session_id}/{transition}",
    response_model=ClinicSessionResponse,
)
def transition_clinic_session(
    session_id: uuid.UUID,
    transition: str,
    _parent: str = Depends(verify_admin),
    service: ClinicGameService = Depends(get_clinic_admin_service),
) -> ClinicSessionResponse:
    state = service.get_by_id(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Clinic session not found")
    try:
        state = service.set_status(state.conversation_id, transition)
    except ClinicConversationError as exc:
        raise HTTPException(status_code=409, detail="Clinic transition is unavailable") from exc
    return serialize_clinic_session(service, state)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def reset_clinic_session(
    session_id: uuid.UUID,
    _parent: str = Depends(verify_admin),
    service: ClinicGameService = Depends(get_clinic_admin_service),
) -> Response:
    try:
        service.reset(session_id)
    except ClinicConversationError as exc:
        raise HTTPException(status_code=404, detail="Clinic session not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
