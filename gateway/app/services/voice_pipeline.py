"""Shared provider-neutral STT/TTS stages for every voice-capable turn."""

import asyncio
import time
from collections.abc import AsyncIterator
from uuid import UUID

from gateway.app.observability.request_tracing import request_trace_registry
from gateway.app.providers.contracts import (
    SpeechRecognitionProvider,
    SpeechSynthesisProvider,
)
from gateway.app.providers.schemas import SpeechRequest, SpeechResponse, TranscriptionRequest
from gateway.app.services.voice_execution import (
    VoiceExecutionPolicy,
    VoiceStageTimeoutError,
    run_with_stage_timeout,
)
from gateway.app.services.voice_streaming import (
    PreparedVoiceResponse,
    VoiceTurnTelemetry,
    stream_speech_events,
)


class VoiceInputError(ValueError):
    """Raised when a recording cannot produce a useful transcript."""


class VoicePipeline:
    """Run common speech stages with consistent tracing, budgets, and metrics."""

    def __init__(
        self,
        recognition_provider: SpeechRecognitionProvider,
        synthesis_provider: SpeechSynthesisProvider,
        execution_policy: VoiceExecutionPolicy,
    ) -> None:
        self._recognition_provider = recognition_provider
        self._synthesis_provider = synthesis_provider
        self._execution_policy = execution_policy

    async def transcribe(
        self,
        request: TranscriptionRequest,
        telemetry: VoiceTurnTelemetry,
        request_id: UUID,
    ):
        """Run STT and emit the same content-free trace in every voice mode."""

        started_at = time.perf_counter()
        request_trace_registry.event(request_id, "stt", "started")
        try:
            result = await run_with_stage_timeout(
                self._recognition_provider.transcribe_audio(request),
                seconds=self._execution_policy.stt_timeout_seconds,
                stage="stt",
            )
        except Exception as exc:
            request_trace_registry.event(
                request_id,
                "stt",
                "error",
                duration_ms=round((time.perf_counter() - started_at) * 1000),
                error_code=(
                    "timeout" if isinstance(exc, VoiceStageTimeoutError) else "provider_error"
                ),
            )
            raise
        finally:
            telemetry.stt_duration_ms = round((time.perf_counter() - started_at) * 1000)
        request_trace_registry.event(
            request_id,
            "stt",
            "success",
            duration_ms=telemetry.stt_duration_ms,
        )
        return result

    async def synthesize(
        self,
        prepared: PreparedVoiceResponse,
    ) -> SpeechResponse:
        """Run non-streaming TTS and finalize its request trace."""

        telemetry = prepared.telemetry
        request_id = prepared.request_id
        started_at = time.perf_counter()
        request_trace_registry.event(request_id, "tts", "started")
        try:
            speech = await run_with_stage_timeout(
                self._synthesis_provider.synthesize_speech(
                    SpeechRequest(
                        text=prepared.text,
                        voice=prepared.voice,
                        request_id=request_id,
                    )
                ),
                seconds=self._execution_policy.tts_timeout_seconds,
                stage="tts",
            )
        except Exception as exc:
            telemetry.tts_duration_ms = round((time.perf_counter() - started_at) * 1000)
            timed_out = isinstance(exc, VoiceStageTimeoutError)
            telemetry.record(
                status="error",
                error_stage="tts_timeout" if timed_out else "tts",
            )
            request_trace_registry.event(
                request_id,
                "tts",
                "error",
                duration_ms=telemetry.tts_duration_ms,
                error_code="timeout" if timed_out else "provider_error",
            )
            request_trace_registry.finish(
                request_id,
                "error",
                error_code="tts_timeout" if timed_out else "tts",
            )
            raise
        finally:
            telemetry.tts_duration_ms = round((time.perf_counter() - started_at) * 1000)

        telemetry.record(status="success")
        request_trace_registry.event(
            request_id,
            "tts",
            "success",
            duration_ms=telemetry.tts_duration_ms,
        )
        request_trace_registry.finish(request_id, "success")
        return speech

    async def stream_synthesis(
        self,
        prepared: PreparedVoiceResponse,
    ) -> AsyncIterator[bytes]:
        """Stream TTS events under the common time budget and request trace."""

        started_at = time.perf_counter()
        request_trace_registry.event(prepared.request_id, "tts", "started")
        try:
            async with asyncio.timeout(self._execution_policy.tts_timeout_seconds):
                async for event in stream_speech_events(
                    prepared,
                    self._synthesis_provider,
                ):
                    yield event
        except TimeoutError as exc:
            raise VoiceStageTimeoutError("tts") from exc
        request_trace_registry.event(
            prepared.request_id,
            "tts",
            "success",
            duration_ms=round((time.perf_counter() - started_at) * 1000),
        )
        request_trace_registry.finish(prepared.request_id, "success")
