"""Child API for deterministic pretend-clinic sessions."""

import uuid

from fastapi import APIRouter, Depends, HTTPException

from gateway.app.clinic import ClinicCaseNotFoundError, ClinicConversationError, ClinicGameService
from gateway.app.clinic.metrics import clinic_metrics_registry
from gateway.app.dependencies import get_clinic_service, get_conversation_service
from gateway.app.models import MessageRole
from gateway.app.models.clinic_session import ClinicSession
from gateway.app.schemas.clinic import (
    ClinicActionResponse,
    ClinicCaseListResponse,
    ClinicCaseSummaryResponse,
    ClinicSessionResponse,
    ClinicStateResponse,
    ClinicTurnResponse,
    ClinicVitalResponse,
)
from gateway.app.schemas.conversations import MessageResponse
from gateway.app.services.conversation_service import ConversationService

router = APIRouter(prefix="/v1/clinic", tags=["clinic"])


def serialize_clinic_session(
    service: ClinicGameService,
    session: ClinicSession,
) -> ClinicSessionResponse:
    definition = service.definition_for(session)
    completed = {event.action_id for event in session.procedure_events}
    return ClinicSessionResponse(
        id=session.id,
        conversation_id=session.conversation_id,
        case_id=session.case_id,
        case_version=session.case_version,
        title=definition.title,
        patient_name=definition.patient_name,
        patient_icon=definition.patient_icon,
        color=definition.color,
        status=session.status,
        vitals=[
            ClinicVitalResponse.model_validate(session.vital_snapshot[item.id])
            for item in definition.vitals
        ],
        actions=[
            ClinicActionResponse(
                id=action.id,
                icon=action.icon,
                label=action.label,
                completed=action.id in completed,
            )
            for action in definition.actions
        ],
        started_at=session.started_at,
        updated_at=session.updated_at,
        expires_at=session.expires_at,
    )


@router.get("/cases", response_model=ClinicCaseListResponse)
def list_clinic_cases(
    service: ClinicGameService = Depends(get_clinic_service),
) -> ClinicCaseListResponse:
    return ClinicCaseListResponse(
        schema_version=service.catalog.schema_version,
        items=[
            ClinicCaseSummaryResponse(
                id=item.id,
                version=item.version,
                title=item.title,
                short_title=item.short_title,
                description=item.description,
                patient_name=item.patient_name,
                patient_icon=item.patient_icon,
                color=item.color,
            )
            for item in service.catalog.list()
        ],
    )


@router.get("/conversations/{conversation_id}", response_model=ClinicStateResponse)
def get_clinic_state(
    conversation_id: uuid.UUID,
    service: ClinicGameService = Depends(get_clinic_service),
) -> ClinicStateResponse:
    state = service.get(conversation_id)
    return ClinicStateResponse(session=serialize_clinic_session(service, state) if state else None)


@router.post(
    "/conversations/{conversation_id}/cases/{case_id}/start",
    response_model=ClinicTurnResponse,
)
def start_clinic_case(
    conversation_id: uuid.UUID,
    case_id: str,
    service: ClinicGameService = Depends(get_clinic_service),
    conversation: ConversationService = Depends(get_conversation_service),
) -> ClinicTurnResponse:
    try:
        state = service.start(conversation_id, case_id)
        definition = service.definition_for(state)
    except ClinicCaseNotFoundError as exc:
        clinic_metrics_registry.record("start", succeeded=False)
        raise HTTPException(status_code=404, detail="Clinic case is unavailable") from exc
    except ClinicConversationError as exc:
        clinic_metrics_registry.record("start", succeeded=False)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    clinic_metrics_registry.record("start", succeeded=True)
    message = conversation.create_message(
        conversation_id, MessageRole.ASSISTANT, definition.opening_text
    )
    return ClinicTurnResponse(
        session=serialize_clinic_session(service, state),
        message=MessageResponse.model_validate(message),
    )


@router.post(
    "/conversations/{conversation_id}/actions/{action_id}",
    response_model=ClinicTurnResponse,
)
def perform_clinic_action(
    conversation_id: uuid.UUID,
    action_id: str,
    service: ClinicGameService = Depends(get_clinic_service),
    conversation: ConversationService = Depends(get_conversation_service),
) -> ClinicTurnResponse:
    try:
        result = service.perform_action(conversation_id, action_id)
    except (ClinicCaseNotFoundError, ClinicConversationError) as exc:
        clinic_metrics_registry.record("action", succeeded=False)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    clinic_metrics_registry.record("action", succeeded=True)
    message = conversation.create_message(conversation_id, MessageRole.ASSISTANT, result.response)
    return ClinicTurnResponse(
        session=serialize_clinic_session(service, result.session),
        message=MessageResponse.model_validate(message),
        repeated=not result.created,
    )


@router.post(
    "/conversations/{conversation_id}/{transition}",
    response_model=ClinicStateResponse,
)
def transition_clinic_case(
    conversation_id: uuid.UUID,
    transition: str,
    service: ClinicGameService = Depends(get_clinic_service),
) -> ClinicStateResponse:
    try:
        state = service.set_status(conversation_id, transition)
    except ClinicConversationError as exc:
        clinic_metrics_registry.record(transition, succeeded=False)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    clinic_metrics_registry.record(transition, succeeded=True)
    return ClinicStateResponse(session=serialize_clinic_session(service, state))
