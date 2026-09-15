"""Protected pretend-clinic catalog preview and session controls."""

import uuid
from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from pydantic import ValidationError
from sqlalchemy.orm import Session

from gateway.admin.auth import verify_admin
from gateway.admin.clinic_schemas import (
    ClinicAdminCatalogResponse,
    ClinicAdminSessionsResponse,
)
from gateway.app.clinic import ClinicCaseCatalog, ClinicCaseNotFoundError, ClinicConversationError, ClinicGameService
from gateway.app.config import get_settings
from gateway.app.db.session import get_session_factory
from gateway.app.routers.clinic import serialize_clinic_session
from gateway.app.schemas.clinic import ClinicSessionResponse
from gateway.admin.clinic_draft_service import ClinicDraftService
from gateway.app.models.clinic_scenario_draft import ClinicScenarioDraft

router = APIRouter(prefix="/api/clinic", tags=["clinic administration"])


class ClinicDraftWriteRequest(BaseModel):
    case_id: str = Field(pattern=r"^[a-z0-9_]+$")
    payload: dict[str, str]


class ClinicDraftResponse(BaseModel):
    id: uuid.UUID
    case_id: str
    version: int
    status: str
    payload: dict[str, str]
    created_by: str
    created_at: object
    published_at: object | None


def _draft_response(draft: ClinicScenarioDraft) -> ClinicDraftResponse:
    return ClinicDraftResponse.model_validate(draft, from_attributes=True)


def get_clinic_admin_session() -> Generator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except ClinicCaseNotFoundError:
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


@router.get("/drafts", response_model=list[ClinicDraftResponse])
def list_clinic_drafts(
    _parent: str = Depends(verify_admin),
    session: Session = Depends(get_clinic_admin_session),
) -> list[ClinicDraftResponse]:
    from sqlalchemy import select
    return [_draft_response(item) for item in session.scalars(select(ClinicScenarioDraft).order_by(ClinicScenarioDraft.created_at.desc()))]


@router.post("/drafts", response_model=ClinicDraftResponse, status_code=status.HTTP_201_CREATED)
def create_clinic_draft(
    payload: ClinicDraftWriteRequest,
    _parent: str = Depends(verify_admin),
    session: Session = Depends(get_clinic_admin_session),
) -> ClinicDraftResponse:
    try:
        ClinicCaseCatalog().get(payload.case_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Clinic case is unavailable")
    try:
        return _draft_response(ClinicDraftService(session).create(payload.case_id, payload.payload))
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Clinic draft does not pass validation") from exc


@router.post("/drafts/{draft_id}/publish", response_model=ClinicDraftResponse)
def publish_clinic_draft(
    draft_id: uuid.UUID,
    _parent: str = Depends(verify_admin),
    session: Session = Depends(get_clinic_admin_session),
) -> ClinicDraftResponse:
    try:
        return _draft_response(ClinicDraftService(session).publish(draft_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Clinic draft not found") from exc


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
