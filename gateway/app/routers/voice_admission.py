"""Shared HTTP admission boundary for voice and multimodal turns."""

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import HTTPException, status

from gateway.app.observability.request_tracing import request_trace_registry
from gateway.app.services.voice_execution import (
    DuplicateVoiceRequestError,
    VoiceAdmissionLease,
    VoiceCapacityError,
    voice_admission_controller,
)


def admit_voice_request(
    request_id: UUID,
    *,
    mode: str,
    max_in_flight: int,
) -> VoiceAdmissionLease:
    """Acquire one turn slot or return a stable child-safe HTTP error."""

    try:
        lease = voice_admission_controller.acquire(
            request_id,
            max_in_flight=max_in_flight,
        )
    except DuplicateVoiceRequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This voice request was already sent",
            headers={"X-Request-ID": str(request_id)},
        ) from exc
    except VoiceCapacityError as exc:
        request_trace_registry.start(request_id, mode)
        request_trace_registry.event(
            request_id,
            "admission",
            "error",
            error_code="voice_busy",
        )
        request_trace_registry.finish(request_id, "error", error_code="voice_busy")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Voice is busy; try again shortly",
            headers={"Retry-After": "3", "X-Request-ID": str(request_id)},
        ) from exc
    request_trace_registry.start(request_id, mode)
    request_trace_registry.event(request_id, "admission", "accepted")
    return lease


async def release_after_stream(
    stream: AsyncIterator[bytes],
    lease: VoiceAdmissionLease,
) -> AsyncIterator[bytes]:
    """Hold capacity until a stream completes, fails, or is cancelled."""

    try:
        async for item in stream:
            yield item
    finally:
        lease.release()
