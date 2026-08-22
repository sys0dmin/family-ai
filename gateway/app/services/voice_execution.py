"""Bounded, content-free execution policy for voice turns."""

from __future__ import annotations

import asyncio
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID


class VoiceAdmissionError(RuntimeError):
    """Base class for a turn rejected before provider work starts."""


class DuplicateVoiceRequestError(VoiceAdmissionError):
    """Raised when the same anonymous request ID is submitted again."""


class VoiceCapacityError(VoiceAdmissionError):
    """Raised when the bounded in-flight capacity is exhausted."""


class VoiceStageTimeoutError(TimeoutError):
    """Raised when one provider-neutral voice stage exceeds its budget."""

    def __init__(self, stage: str) -> None:
        super().__init__(f"Voice stage exceeded its time budget: {stage}")
        self.stage = stage


@dataclass(frozen=True)
class VoiceExecutionPolicy:
    """Provider-neutral runtime budgets derived from the J3710 baseline."""

    stt_timeout_seconds: float = 60.0
    llm_timeout_seconds: float = 20.0
    tts_timeout_seconds: float = 30.0


class VoiceAdmissionLease:
    """Idempotent capacity lease owned for the complete response lifecycle."""

    def __init__(self, controller: VoiceAdmissionController, request_id: UUID) -> None:
        self._controller = controller
        self.request_id = request_id
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._controller.release(self.request_id)


class VoiceAdmissionController:
    """Reject overload and duplicate turns without retaining child content."""

    def __init__(self, duplicate_ttl_minutes: int = 5, max_recent: int = 512) -> None:
        self._duplicate_ttl = timedelta(minutes=duplicate_ttl_minutes)
        self._max_recent = max_recent
        self._active: set[UUID] = set()
        self._recent: OrderedDict[UUID, datetime] = OrderedDict()
        self._duplicate_rejections = 0
        self._capacity_rejections = 0
        self._lock = threading.Lock()

    def acquire(self, request_id: UUID, *, max_in_flight: int) -> VoiceAdmissionLease:
        now = datetime.now(UTC)
        with self._lock:
            self._prune_locked(now)
            if request_id in self._active or request_id in self._recent:
                self._duplicate_rejections += 1
                raise DuplicateVoiceRequestError
            if len(self._active) >= max_in_flight:
                self._capacity_rejections += 1
                raise VoiceCapacityError
            self._active.add(request_id)
        return VoiceAdmissionLease(self, request_id)

    def release(self, request_id: UUID) -> None:
        now = datetime.now(UTC)
        with self._lock:
            if request_id not in self._active:
                return
            self._active.remove(request_id)
            self._recent[request_id] = now
            self._recent.move_to_end(request_id)
            while len(self._recent) > self._max_recent:
                self._recent.popitem(last=False)

    def snapshot(self, *, max_in_flight: int) -> dict[str, int]:
        with self._lock:
            self._prune_locked(datetime.now(UTC))
            return {
                "active": len(self._active),
                "capacity": max_in_flight,
                "available": max(0, max_in_flight - len(self._active)),
                "duplicate_rejections": self._duplicate_rejections,
                "capacity_rejections": self._capacity_rejections,
            }

    def reset(self) -> None:
        """Clear process-local state for deterministic tests."""

        with self._lock:
            self._active.clear()
            self._recent.clear()
            self._duplicate_rejections = 0
            self._capacity_rejections = 0

    def _prune_locked(self, now: datetime) -> None:
        cutoff = now - self._duplicate_ttl
        while self._recent:
            request_id, completed_at = next(iter(self._recent.items()))
            if completed_at >= cutoff:
                break
            self._recent.pop(request_id, None)


voice_admission_controller = VoiceAdmissionController()


def voice_timeout_message(stage: str) -> str:
    """Return a truthful child-friendly explanation for the failed stage."""

    if stage == "stt":
        return "Я не успела тебя расслышать. Скажи, пожалуйста, ещё раз покороче."
    return "Ответ не успел прийти. Давай немного подождём и попробуем ещё раз."


async def run_with_stage_timeout(awaitable, *, seconds: float, stage: str):
    """Await one provider-neutral stage and translate asyncio timeout details."""

    try:
        async with asyncio.timeout(seconds):
            return await awaitable
    except TimeoutError as exc:
        raise VoiceStageTimeoutError(stage) from exc
