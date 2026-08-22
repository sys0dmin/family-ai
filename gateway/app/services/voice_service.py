"""Application service for a complete voice conversation turn."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from gateway.app.observability.request_tracing import request_trace_registry
from gateway.app.observability.voice_metrics import VoiceMetricsRegistry
from gateway.app.providers.contracts import (
    SpeechRecognitionProvider,
    SpeechSynthesisProvider,
)
from gateway.app.providers.schemas import (
    SpeechRequest,
    SpeechResponse,
    TranscriptionRequest,
    TranscriptionResponse,
)
from gateway.app.services.conversation_service import ConversationService
from gateway.app.services.music_recognition_service import MusicRecognitionService
from gateway.app.services.turn_diagnostics import TurnDiagnostics
from gateway.app.services.voice_execution import (
    VoiceExecutionPolicy,
    VoiceStageTimeoutError,
    run_with_stage_timeout,
    voice_timeout_message,
)
from gateway.app.services.voice_streaming import (
    VOICE_RESPONSE_CONTEXT,
    PreparedVoiceResponse,
    VoiceTurnTelemetry,
    combine_runtime_context,
    encode_stream_event,
    stream_speech_events,
    voice_stream_registry,
)

logger = logging.getLogger(__name__)


class VoiceInputError(ValueError):
    """Raised when a recording cannot produce a useful transcript."""


@dataclass(frozen=True)
class VoiceTurnResult:
    """Synthesized speech linked to the stored assistant message."""

    speech: SpeechResponse
    message_id: UUID


class VoiceService:
    """Coordinate STT, the safe conversation flow, and TTS."""

    def __init__(
        self,
        recognition_provider: SpeechRecognitionProvider,
        synthesis_provider: SpeechSynthesisProvider,
        conversation_service: ConversationService,
        music_recognition_service: MusicRecognitionService | None = None,
        metrics: VoiceMetricsRegistry | None = None,
        execution_policy: VoiceExecutionPolicy | None = None,
    ) -> None:
        self._recognition_provider = recognition_provider
        self._synthesis_provider = synthesis_provider
        self._conversation_service = conversation_service
        self._music_recognition_service = music_recognition_service
        self._metrics = metrics or VoiceMetricsRegistry()
        self._execution_policy = execution_policy or VoiceExecutionPolicy()

    async def process_voice_turn(
        self,
        conversation_id: UUID,
        audio_content: bytes,
        filename: str,
        content_type: str,
        language: str = "ru",
        recording_duration_ms: int | None = None,
        request_id: UUID | None = None,
    ) -> VoiceTurnResult:
        """Run one audio request through STT, conversation safety, and TTS."""

        telemetry = VoiceTurnTelemetry(
            metrics=self._metrics,
            mode="voice",
            recording_duration_ms=recording_duration_ms,
            streamed=False,
        )
        request_id = request_trace_registry.request_id(request_id)
        prepared = await self._prepare_voice_turn(
            conversation_id=conversation_id,
            audio_content=audio_content,
            filename=filename,
            content_type=content_type,
            language=language,
            telemetry=telemetry,
            optimize_for_stream=False,
            request_id=request_id,
        )
        tts_started_at = time.perf_counter()
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
        except VoiceStageTimeoutError:
            telemetry.tts_duration_ms = round((time.perf_counter() - tts_started_at) * 1000)
            telemetry.record(status="error", error_stage="tts_timeout")
            request_trace_registry.event(
                request_id,
                "tts",
                "error",
                duration_ms=telemetry.tts_duration_ms,
                error_code="timeout",
            )
            request_trace_registry.finish(request_id, "error", error_code="tts_timeout")
            raise
        except Exception:
            telemetry.tts_duration_ms = round((time.perf_counter() - tts_started_at) * 1000)
            telemetry.record(status="error", error_stage="tts")
            request_trace_registry.event(
                request_id,
                "tts",
                "error",
                duration_ms=telemetry.tts_duration_ms,
                error_code="provider_error",
            )
            request_trace_registry.finish(request_id, "error", error_code="tts")
            raise
        finally:
            telemetry.tts_duration_ms = round((time.perf_counter() - tts_started_at) * 1000)
        telemetry.record(status="success")
        request_trace_registry.event(
            request_id,
            "tts",
            "success",
            duration_ms=telemetry.tts_duration_ms,
        )
        request_trace_registry.finish(request_id, "success")
        logger.info(
            "voice_synthesis_completed",
            extra={"audio_bytes": len(speech.audio_content)},
        )
        return VoiceTurnResult(speech=speech, message_id=prepared.message_id)

    async def stream_voice_turn(
        self,
        conversation_id: UUID,
        audio_content: bytes,
        filename: str,
        content_type: str,
        language: str = "ru",
        recording_duration_ms: int | None = None,
        request_id: UUID | None = None,
    ) -> AsyncIterator[bytes]:
        """Yield NDJSON events and stop remaining work when the turn is cancelled."""

        telemetry = VoiceTurnTelemetry(
            metrics=self._metrics,
            mode="voice",
            recording_duration_ms=recording_duration_ms,
            streamed=True,
        )
        request_id = request_trace_registry.request_id(request_id)
        voice_stream_registry.register(telemetry.turn_id)
        yield encode_stream_event("started", turn_id=str(telemetry.turn_id))
        try:
            prepared = await self._prepare_voice_turn(
                conversation_id=conversation_id,
                audio_content=audio_content,
                filename=filename,
                content_type=content_type,
                language=language,
                telemetry=telemetry,
                optimize_for_stream=True,
                request_id=request_id,
            )
            tts_started_at = time.perf_counter()
            request_trace_registry.event(request_id, "tts", "started")
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
                request_id,
                "tts",
                "success",
                duration_ms=round((time.perf_counter() - tts_started_at) * 1000),
            )
            request_trace_registry.finish(request_id, "success")
        except asyncio.CancelledError:
            telemetry.record(
                status="cancelled",
                error_stage="cancelled",
                cancelled=True,
            )
            request_trace_registry.finish(request_id, "cancelled")
            raise
        except VoiceInputError:
            request_trace_registry.finish(request_id, "error", error_code="stt")
            yield encode_stream_event(
                "error",
                code="speech_not_recognized",
                message="Не удалось расслышать вопрос. Попробуем ещё раз.",
            )
        except VoiceStageTimeoutError as exc:
            telemetry.record(status="error", error_stage=f"{exc.stage}_timeout")
            request_trace_registry.finish(
                request_id,
                "error",
                error_code=f"{exc.stage}_timeout",
            )
            yield encode_stream_event(
                "error",
                code="voice_timeout",
                message=voice_timeout_message(exc.stage),
            )
        except Exception:
            telemetry.record(status="error", error_stage="tts")
            logger.exception("streaming_voice_turn_failed")
            request_trace_registry.finish(request_id, "error", error_code="provider_error")
            yield encode_stream_event(
                "error",
                code="provider_unavailable",
                message="Не получилось подготовить ответ. Давай попробуем ещё раз.",
            )
        finally:
            voice_stream_registry.unregister(telemetry.turn_id)

    async def _prepare_voice_turn(
        self,
        *,
        conversation_id: UUID,
        audio_content: bytes,
        filename: str,
        content_type: str,
        language: str,
        telemetry: VoiceTurnTelemetry,
        optimize_for_stream: bool,
        request_id: UUID,
    ) -> PreparedVoiceResponse:
        stage = "stt"
        diagnostics = TurnDiagnostics()
        active_agent = self._conversation_service.get_conversation_agent(conversation_id)
        transcription_request = TranscriptionRequest(
            audio_content=audio_content,
            filename=filename,
            content_type=content_type,
            language=language,
            request_id=request_id,
        )

        async def transcribe() -> TranscriptionResponse:
            started_at = time.perf_counter()
            request_trace_registry.event(request_id, "stt", "started")
            try:
                result = await run_with_stage_timeout(
                    self._recognition_provider.transcribe_audio(transcription_request),
                    seconds=self._execution_policy.stt_timeout_seconds,
                    stage="stt",
                )
            except VoiceStageTimeoutError:
                request_trace_registry.event(
                    request_id,
                    "stt",
                    "error",
                    duration_ms=round((time.perf_counter() - started_at) * 1000),
                    error_code="timeout",
                )
                raise
            except Exception:
                request_trace_registry.event(
                    request_id,
                    "stt",
                    "error",
                    duration_ms=round((time.perf_counter() - started_at) * 1000),
                    error_code="provider_error",
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

        try:
            recognition_task = None
            if self._music_recognition_service is not None:
                recognition_task = self._music_recognition_service.recognize_for_agent(
                    agent=active_agent,
                    audio_content=audio_content,
                    filename=filename,
                    content_type=content_type,
                )
            if recognition_task is None:
                transcription = await transcribe()
                recognition = None
            else:
                transcription, recognition = await asyncio.gather(
                    transcribe(),
                    recognition_task,
                )

            telemetry.stt_confidence = transcription.confidence
            telemetry.recording_duration_ms = (
                transcription.duration_ms or telemetry.recording_duration_ms
            )
            transcript = transcription.text.strip()
            if not transcript and recognition is None:
                raise VoiceInputError("Audio did not contain recognizable speech")
            if not transcript:
                transcript = "[Лера напела мелодию без слов]"

            logger.info(
                "voice_transcription_completed",
                extra={
                    "transcript_characters": len(transcript),
                    "confidence": telemetry.stt_confidence,
                    "recording_duration_ms": telemetry.recording_duration_ms,
                },
            )

            stage = "llm"
            request_trace_registry.event(request_id, "llm", "started")
            ai_message = await run_with_stage_timeout(
                self._conversation_service.process_turn(
                    conversation_id=conversation_id,
                    text=transcript,
                    runtime_context=combine_runtime_context(
                        recognition.prompt_context if recognition else None,
                        VOICE_RESPONSE_CONTEXT if optimize_for_stream else None,
                    ),
                    diagnostics=diagnostics,
                    request_id=request_id,
                ),
                seconds=self._execution_policy.llm_timeout_seconds,
                stage="llm",
            )
            telemetry.llm_duration_ms = diagnostics.llm_duration_ms
            request_trace_registry.event(
                request_id,
                "llm",
                "success",
                duration_ms=telemetry.llm_duration_ms,
            )
            return PreparedVoiceResponse(
                message_id=ai_message.id,
                text=ai_message.content,
                voice=active_agent.tts_voice,
                telemetry=telemetry,
                request_id=request_id,
            )
        except asyncio.CancelledError:
            telemetry.record(
                status="cancelled",
                error_stage=stage,
                cancelled=True,
            )
            raise
        except Exception as exc:
            telemetry.llm_duration_ms = diagnostics.llm_duration_ms
            telemetry.record(status="error", error_stage=stage)
            if stage == "llm":
                request_trace_registry.event(
                    request_id,
                    "llm",
                    "error",
                    duration_ms=telemetry.llm_duration_ms,
                    error_code=(
                        "timeout" if isinstance(exc, VoiceStageTimeoutError) else "provider_error"
                    ),
                )
            raise

    async def synthesize_text(
        self,
        conversation_id: UUID,
        text: str,
        request_id: UUID | None = None,
    ) -> SpeechResponse:
        """Speak existing assistant text with the agent bound to the conversation."""

        active_agent = self._conversation_service.get_conversation_agent(conversation_id)
        return await run_with_stage_timeout(
            self._synthesis_provider.synthesize_speech(
                SpeechRequest(
                    text=text.strip(),
                    voice=active_agent.tts_voice,
                    request_id=request_id,
                )
            ),
            seconds=self._execution_policy.tts_timeout_seconds,
            stage="tts",
        )
