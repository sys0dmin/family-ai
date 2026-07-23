"""Application orchestration for serialized CPU inference."""

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, TypeVar

from family_ai_speech.backends import (
    SpeechToTextBackend,
    TextToSpeechBackend,
    TranscriptionResult,
)
from family_ai_speech.schemas import (
    SpeechRuntimeMetricsResponse,
    StageRuntimeMetrics,
)

ResultT = TypeVar("ResultT")
StageName = Literal["stt", "tts"]


@dataclass
class _StageAccumulator:
    calls: int = 0
    errors: int = 0
    total_processing_ms: float = 0.0
    last_processing_ms: float | None = None
    total_queue_wait_ms: float = 0.0
    last_queue_wait_ms: float | None = None

    def snapshot(self) -> StageRuntimeMetrics:
        return StageRuntimeMetrics(
            calls=self.calls,
            errors=self.errors,
            average_processing_ms=(
                round(self.total_processing_ms / self.calls, 1)
                if self.calls
                else None
            ),
            last_processing_ms=self.last_processing_ms,
            average_queue_wait_ms=(
                round(self.total_queue_wait_ms / self.calls, 1)
                if self.calls
                else None
            ),
            last_queue_wait_ms=self.last_queue_wait_ms,
        )


class LocalSpeechService:
    """Keep model work off the event loop and avoid CPU oversubscription."""

    def __init__(
        self,
        stt: SpeechToTextBackend,
        tts: TextToSpeechBackend,
    ) -> None:
        self._stt = stt
        self._tts = tts
        self._inference_lock = asyncio.Lock()
        self._started_at = time.perf_counter()
        self._queue_depth = 0
        self._active_stage: StageName | None = None
        self._stage_metrics = {
            "stt": _StageAccumulator(),
            "tts": _StageAccumulator(),
        }

    async def transcribe(
        self,
        audio: bytes,
        language: str,
        prompt: str | None = None,
    ) -> TranscriptionResult:
        return await self._run_serialized(
            "stt",
            self._stt.transcribe,
            audio,
            language,
            prompt,
        )

    async def synthesize(self, text: str, voice: str | None) -> bytes:
        return await self._run_serialized(
            "tts",
            self._tts.synthesize,
            text,
            voice,
        )

    async def benchmark_transcribe(
        self,
        audio: bytes,
        language: str,
        prompt: str | None,
        *,
        beam_size: int,
        vad_filter: bool,
    ) -> TranscriptionResult:
        """Run one low-priority trial while sharing the production inference lock."""

        await asyncio.sleep(0)
        async with self._inference_lock:
            self._active_stage = "stt"
            try:
                return await asyncio.to_thread(
                    self._stt.transcribe_with_options,
                    audio,
                    language,
                    prompt,
                    beam_size=beam_size,
                    vad_filter=vad_filter,
                )
            finally:
                self._active_stage = None

    async def _run_serialized(
        self,
        stage: StageName,
        operation,
        *args,
    ) -> ResultT:
        queued_at = time.perf_counter()
        still_queued = True
        self._queue_depth += 1
        try:
            async with self._inference_lock:
                self._queue_depth -= 1
                still_queued = False
                queue_wait_ms = round((time.perf_counter() - queued_at) * 1000, 1)
                accumulator = self._stage_metrics[stage]
                accumulator.calls += 1
                accumulator.last_queue_wait_ms = queue_wait_ms
                accumulator.total_queue_wait_ms += queue_wait_ms
                self._active_stage = stage
                processing_started = time.perf_counter()
                try:
                    return await asyncio.to_thread(operation, *args)
                except Exception:
                    accumulator.errors += 1
                    raise
                finally:
                    processing_ms = round(
                        (time.perf_counter() - processing_started) * 1000,
                        1,
                    )
                    accumulator.last_processing_ms = processing_ms
                    accumulator.total_processing_ms += processing_ms
                    self._active_stage = None
        finally:
            if still_queued:
                self._queue_depth -= 1

    def metrics_snapshot(self) -> SpeechRuntimeMetricsResponse:
        """Return numeric runtime state without text or audio."""

        return SpeechRuntimeMetricsResponse(
            generated_at=datetime.now(UTC),
            uptime_seconds=round(time.perf_counter() - self._started_at, 1),
            queue_depth=self._queue_depth,
            active_stage=self._active_stage,
            stt=self._stage_metrics["stt"].snapshot(),
            tts=self._stage_metrics["tts"].snapshot(),
        )
