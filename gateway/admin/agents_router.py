"""Protected REST API for agent metadata and immutable prompt revisions."""

import uuid
from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from gateway.admin.agent_schemas import (
    AdminAgentListResponse,
    AdminAgentResponse,
    AgentRevisionResponse,
    AgentUpdateRequest,
    CreateAgentRevisionRequest,
)
from gateway.admin.agent_service import AdminAgentNotFoundError, AdminAgentService
from gateway.admin.auth import verify_admin
from gateway.app.agents.prompts import CHILD_SAFETY_BASE_PROMPT
from gateway.app.db.session import get_session_factory
from gateway.app.models import Agent, AgentRevision

router = APIRouter(prefix="/api/agents", tags=["agent administration"])


def get_agent_admin_session() -> Generator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_agent_admin_service(
    session: Session = Depends(get_agent_admin_session),
) -> AdminAgentService:
    return AdminAgentService(session)


def _revision_response(
    revision: AgentRevision,
    active_revision_id: uuid.UUID | None,
) -> AgentRevisionResponse:
    return AgentRevisionResponse(
        id=revision.id,
        version=revision.version,
        system_prompt=revision.system_prompt,
        created_by=revision.created_by,
        created_at=revision.created_at,
        is_active=revision.id == active_revision_id,
    )


def _agent_response(agent: Agent) -> AdminAgentResponse:
    revisions = sorted(agent.revisions, key=lambda item: item.version, reverse=True)
    return AdminAgentResponse(
        id=agent.id,
        display_name=agent.display_name,
        description=agent.description,
        icon=agent.icon,
        color=agent.color,
        greeting=agent.greeting,
        tts_voice=agent.tts_voice,
        tools=agent.tools or [],
        permissions=agent.permissions or [],
        enabled=agent.enabled,
        sort_order=agent.sort_order,
        active_revision_id=agent.active_revision_id,
        revisions=[
            _revision_response(revision, agent.active_revision_id)
            for revision in revisions
        ],
    )


@router.get("", response_model=AdminAgentListResponse)
def list_agents(
    _user: str = Depends(verify_admin),
    service: AdminAgentService = Depends(get_agent_admin_service),
) -> AdminAgentListResponse:
    return AdminAgentListResponse(
        safety_baseline=CHILD_SAFETY_BASE_PROMPT,
        items=[_agent_response(agent) for agent in service.list_agents()],
    )


@router.patch("/{agent_id}", response_model=AdminAgentResponse)
def update_agent(
    agent_id: str,
    payload: AgentUpdateRequest,
    _user: str = Depends(verify_admin),
    service: AdminAgentService = Depends(get_agent_admin_service),
) -> AdminAgentResponse:
    try:
        service.update_agent(agent_id, payload)
        agent = next(item for item in service.list_agents() if item.id == agent_id)
    except AdminAgentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        ) from exc
    return _agent_response(agent)


@router.post("/{agent_id}/revisions", response_model=AgentRevisionResponse)
def create_revision(
    agent_id: str,
    payload: CreateAgentRevisionRequest,
    _user: str = Depends(verify_admin),
    service: AdminAgentService = Depends(get_agent_admin_service),
) -> AgentRevisionResponse:
    try:
        revision = service.create_revision(agent_id, payload.system_prompt, _user)
    except AdminAgentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        ) from exc
    return _revision_response(revision, None)


@router.post(
    "/{agent_id}/revisions/{revision_id}/publish",
    response_model=AdminAgentResponse,
)
def publish_revision(
    agent_id: str,
    revision_id: uuid.UUID,
    _user: str = Depends(verify_admin),
    service: AdminAgentService = Depends(get_agent_admin_service),
) -> AdminAgentResponse:
    try:
        service.publish_revision(agent_id, revision_id)
        agent = next(item for item in service.list_agents() if item.id == agent_id)
    except AdminAgentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent revision not found",
        ) from exc
    return _agent_response(agent)
