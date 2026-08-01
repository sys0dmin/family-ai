"""Protected activity catalog preview and state reset controls."""

import uuid
from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from gateway.admin.auth import verify_admin
from gateway.app.activities import ActivityCatalog, ActivityService
from gateway.app.activities.service import ActivityConversationError
from gateway.app.config import get_settings
from gateway.app.db.session import get_session_factory
from gateway.app.routers.activities import serialize_activity_session
from gateway.app.schemas.activities import (
    ActivityAdminCatalogResponse,
    ActivityAdminDefinitionResponse,
    ActivityAdminSessionsResponse,
    ActivityAdminStepResponse,
)

router = APIRouter(prefix="/api/activities", tags=["activities"])


def get_activity_admin_session() -> Generator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_activity_admin_service(
    session: Session = Depends(get_activity_admin_session),
) -> ActivityService:
    settings = get_settings()
    return ActivityService(
        session,
        ActivityCatalog(),
        retention_hours=settings.activity_retention_hours,
    )


@router.get("/catalog", response_model=ActivityAdminCatalogResponse)
def activity_catalog(
    _parent: str = Depends(verify_admin),
    service: ActivityService = Depends(get_activity_admin_service),
) -> ActivityAdminCatalogResponse:
    return ActivityAdminCatalogResponse(
        schema_version=service.catalog.schema_version,
        items=[
            ActivityAdminDefinitionResponse(
                id=item.id,
                version=item.version,
                agent_id=item.agent_id,
                title=item.title,
                short_title=item.short_title,
                description=item.description,
                icon=item.icon,
                color=item.color,
                total_steps=len(item.steps),
                opening_text=item.opening_text,
                completion_summary=item.completion_summary,
                steps=[
                    ActivityAdminStepResponse.model_validate(step.model_dump())
                    for step in item.steps
                ],
            )
            for item in service.catalog.list()
        ],
    )


@router.get("/sessions", response_model=ActivityAdminSessionsResponse)
def activity_sessions(
    _parent: str = Depends(verify_admin),
    service: ActivityService = Depends(get_activity_admin_service),
) -> ActivityAdminSessionsResponse:
    service.purge_expired()
    return ActivityAdminSessionsResponse(
        items=[serialize_activity_session(service, item) for item in service.list_sessions()]
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def reset_activity_session(
    session_id: uuid.UUID,
    _parent: str = Depends(verify_admin),
    service: ActivityService = Depends(get_activity_admin_service),
) -> Response:
    try:
        service.reset(session_id)
    except ActivityConversationError as exc:
        raise HTTPException(status_code=404, detail="Activity session not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
