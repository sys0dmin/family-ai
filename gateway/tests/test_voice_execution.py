"""Tests for bounded and duplicate-safe voice execution."""

import asyncio
from uuid import uuid4

import pytest

from gateway.app.routers.voice_admission import release_after_stream
from gateway.app.services.voice_execution import (
    DuplicateVoiceRequestError,
    VoiceAdmissionController,
    VoiceCapacityError,
)


def test_admission_bounds_total_in_flight_turns() -> None:
    controller = VoiceAdmissionController()
    first = controller.acquire(uuid4(), max_in_flight=2)
    second = controller.acquire(uuid4(), max_in_flight=2)

    with pytest.raises(VoiceCapacityError):
        controller.acquire(uuid4(), max_in_flight=2)

    assert controller.snapshot(max_in_flight=2) == {
        "active": 2,
        "capacity": 2,
        "available": 0,
        "duplicate_rejections": 0,
        "capacity_rejections": 1,
    }
    first.release()
    second.release()


def test_admission_rejects_active_and_recent_duplicate() -> None:
    controller = VoiceAdmissionController()
    request_id = uuid4()
    lease = controller.acquire(request_id, max_in_flight=2)

    with pytest.raises(DuplicateVoiceRequestError):
        controller.acquire(request_id, max_in_flight=2)
    lease.release()
    with pytest.raises(DuplicateVoiceRequestError):
        controller.acquire(request_id, max_in_flight=2)

    assert controller.snapshot(max_in_flight=2)["duplicate_rejections"] == 2


def test_release_is_idempotent() -> None:
    controller = VoiceAdmissionController()
    lease = controller.acquire(uuid4(), max_in_flight=1)

    lease.release()
    lease.release()

    assert controller.snapshot(max_in_flight=1)["active"] == 0


def test_stream_close_releases_admission_capacity() -> None:
    async def scenario() -> None:
        controller = VoiceAdmissionController()
        lease = controller.acquire(uuid4(), max_in_flight=1)

        async def source():
            yield b"event\n"
            yield b"unexpected\n"

        stream = release_after_stream(source(), lease)
        assert await anext(stream) == b"event\n"

        await stream.aclose()

        assert controller.snapshot(max_in_flight=1)["active"] == 0

    asyncio.run(scenario())
