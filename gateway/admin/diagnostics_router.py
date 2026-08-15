"""Protected privacy-safe recent request diagnostics."""

import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from gateway.admin.auth import verify_admin
from gateway.app.observability.request_tracing import (
    RequestTrace,
    RequestTraceRegistry,
    request_trace_registry,
)

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


class TraceEventResponse(BaseModel):
    occurred_at: datetime
    stage: str
    status: str
    duration_ms: int | None
    error_code: str | None
    service: str


class RequestTraceResponse(BaseModel):
    request_id: UUID
    mode: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    events: list[TraceEventResponse]


def get_trace_registry() -> RequestTraceRegistry:
    return request_trace_registry


def _response(trace: RequestTrace) -> RequestTraceResponse:
    return RequestTraceResponse(
        request_id=trace.request_id,
        mode=trace.mode,
        started_at=trace.started_at,
        completed_at=trace.completed_at,
        status=trace.status,
        events=[
            TraceEventResponse.model_validate(event, from_attributes=True) for event in trace.events
        ],
    )


@router.get("/traces", response_model=list[RequestTraceResponse])
def list_traces(
    failed_only: bool = Query(default=True),
    _user: str = Depends(verify_admin),
    registry: RequestTraceRegistry = Depends(get_trace_registry),
) -> list[RequestTraceResponse]:
    return [_response(item) for item in registry.list(failed_only=failed_only)]


@router.get("/traces/{request_id}", response_model=RequestTraceResponse)
def get_trace(
    request_id: UUID,
    _user: str = Depends(verify_admin),
    registry: RequestTraceRegistry = Depends(get_trace_registry),
) -> RequestTraceResponse:
    trace = registry.get(request_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Technical trace not found")
    return _response(trace)


@router.get("/bundle")
def export_bundle(
    _user: str = Depends(verify_admin),
    registry: RequestTraceRegistry = Depends(get_trace_registry),
) -> Response:
    traces = [_response(item).model_dump(mode="json") for item in registry.list()]
    payload = {
        "schema": "family-ai-diagnostics/1",
        "generated_at": datetime.now(UTC).isoformat(),
        "privacy": {
            "contains_messages": False,
            "contains_audio": False,
            "contains_images": False,
            "contains_secrets": False,
        },
        "summary": {
            "trace_count": len(traces),
            "failed_count": sum(item["status"] in {"error", "cancelled"} for item in traces),
        },
        "traces": traces,
    }
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="family-ai-diagnostics.json"',
            "Cache-Control": "no-store",
        },
    )
