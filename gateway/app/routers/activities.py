"""Public catalog and lifecycle endpoints for short activities."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from gateway.app.activities.catalog import ActivityNotFoundError
from gateway.app.activities.service import ActivityConversationError, ActivityService
from gateway.app.dependencies import get_activity_service, get_conversation_service
from gateway.app.models import ActivitySession, MessageRole
from gateway.app.schemas.activities import (
    ActivityListResponse,
    ActivitySessionResponse,
    ActivityStartResponse,
    ActivityStateResponse,
    ActivityStopRequest,
    ActivityStopResponse,
    ActivitySummaryResponse,
)
from gateway.app.schemas.conversations import MessageResponse
from gateway.app.services.conversation_service import ConversationService

router = APIRouter(prefix="/v1/activities", tags=["activities"])


def serialize_activity_session(
    service: ActivityService,
    session: ActivitySession,
) -> ActivitySessionResponse:
    definition = service.definition_for(session)
    step = (
        definition.steps[session.current_step]
        if session.status == "active" and session.current_step < len(definition.steps)
        else None
    )
    return ActivitySessionResponse(
        id=session.id,
        conversation_id=session.conversation_id,
        activity_id=session.activity_id,
        activity_version=session.activity_version,
        title=definition.title,
        icon=definition.icon,
        color=definition.color,
        status=session.status,
        current_step=session.current_step,
        total_steps=len(definition.steps),
        current_step_title=step.title if step else None,
        current_step_icon=step.icon if step else None,
        completion_summary=session.completion_summary,
        started_at=session.started_at,
        updated_at=session.updated_at,
        expires_at=session.expires_at,
    )


@router.get("", response_model=ActivityListResponse)
def list_activities(
    agent_id: str | None = Query(default=None, min_length=1, max_length=50),
    service: ActivityService = Depends(get_activity_service),
) -> ActivityListResponse:
    return ActivityListResponse(
        schema_version=service.catalog.schema_version,
        items=[
            ActivitySummaryResponse(
                id=item.id,
                version=item.version,
                agent_id=item.agent_id,
                title=item.title,
                short_title=item.short_title,
                description=item.description,
                icon=item.icon,
                color=item.color,
                total_steps=len(item.steps),
            )
            for item in service.catalog.list(agent_id=agent_id)
        ],
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ActivityStateResponse,
)
def get_activity_state(
    conversation_id: uuid.UUID,
    service: ActivityService = Depends(get_activity_service),
) -> ActivityStateResponse:
    session = service.get(conversation_id)
    return ActivityStateResponse(
        session=serialize_activity_session(service, session) if session else None
    )


@router.post(
    "/conversations/{conversation_id}/{activity_id}/start",
    response_model=ActivityStartResponse,
)
def start_activity(
    conversation_id: uuid.UUID,
    activity_id: str,
    service: ActivityService = Depends(get_activity_service),
    conversation: ConversationService = Depends(get_conversation_service),
) -> ActivityStartResponse:
    try:
        activity_session = service.start(conversation_id, activity_id)
        definition = service.definition_for(activity_session)
    except ActivityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Activity is unavailable") from exc
    except ActivityConversationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    message = conversation.create_message(
        conversation_id,
        MessageRole.ASSISTANT,
        definition.opening_text,
    )
    return ActivityStartResponse(
        session=serialize_activity_session(service, activity_session),
        message=MessageResponse.model_validate(message),
    )


@router.post(
    "/conversations/{conversation_id}/stop",
    response_model=ActivityStopResponse,
)
def stop_activity(
    conversation_id: uuid.UUID,
    payload: ActivityStopRequest,
    service: ActivityService = Depends(get_activity_service),
    conversation: ConversationService = Depends(get_conversation_service),
) -> ActivityStopResponse:
    try:
        activity_session = service.stop(
            conversation_id,
            leave=payload.leave_for_conversation,
        )
    except ActivityConversationError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity session not found",
        ) from exc
    text = (
        "Хорошо, занятие закончилось. Теперь можем просто поговорить о чём захочешь."
        if payload.leave_for_conversation
        else "Хорошо, приключение остановлено. Мы можем вернуться к нему в другой раз."
    )
    message = conversation.create_message(conversation_id, MessageRole.ASSISTANT, text)
    return ActivityStopResponse(
        session=serialize_activity_session(service, activity_session),
        message=MessageResponse.model_validate(message),
    )
