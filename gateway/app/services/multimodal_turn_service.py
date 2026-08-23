"""Application orchestration for one spoken question about one image."""

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
from gateway.app.providers.schemas import SpeechResponse, TranscriptionRequest
from gateway.app.services.conversation_service import ConversationService
from gateway.app.services.image_understanding_service import (
    EphemeralImageObservations,
    ImageUnderstandingNotAllowedError,
    ImageUnderstandingService,
    ImageUnderstandingUnavailableError,
    InvalidImageError,
)
from gateway.app.services.turn_diagnostics import TurnDiagnostics
from gateway.app.services.voice_execution import (
    VoiceExecutionPolicy,
    VoiceStageTimeoutError,
    run_with_stage_timeout,
    voice_timeout_message,
)
from gateway.app.services.voice_pipeline import VoiceInputError, VoicePipeline
from gateway.app.services.voice_streaming import (
    VOICE_RESPONSE_CONTEXT,
    PreparedVoiceResponse,
    VoiceTurnTelemetry,
    combine_runtime_context,
    encode_stream_event,
    voice_stream_registry,
)

logger = logging.getLogger(__name__)

NEUTRAL_VISUAL_QUESTION = (
    "Кратко опиши только надёжно видимые объекты, их положение и важные признаки."
)


@dataclass(frozen=True)
class MultimodalTurnResult:
    """Synthesized response linked to the stored assistant message."""

    speech: SpeechResponse
    message_id: UUID


class MultimodalTurnService:
    """Coordinate independent STT/Vision ports, safe conversation, and TTS."""

    def __init__(
        self,
        recognition_provider: SpeechRecognitionProvider,
        synthesis_provider: SpeechSynthesisProvider,
        image_understanding: ImageUnderstandingService,
        conversation: ConversationService,
        metrics: VoiceMetricsRegistry,
        execution_policy: VoiceExecutionPolicy | None = None,
    ) -> None:
        self._image_understanding = image_understanding
        self._conversation = conversation
        self._metrics = metrics
        self._execution_policy = execution_policy or VoiceExecutionPolicy()
        self._pipeline = VoicePipeline(
            recognition_provider,
            synthesis_provider,
            self._execution_policy,
        )

    async def process_turn(
        self,
        conversation_id: UUID,
        *,
        image_content: bytes,
        image_content_type: str,
        audio_content: bytes,
        audio_filename: str,
        audio_content_type: str,
        language: str = "ru",
        recording_duration_ms: int | None = None,
        request_id: UUID | None = None,
    ) -> MultimodalTurnResult:
        telemetry = VoiceTurnTelemetry(
            metrics=self._metrics,
            mode="multimodal",
            recording_duration_ms=recording_duration_ms,
            streamed=False,
        )
        request_id = request_trace_registry.request_id(request_id)
        prepared = await self._prepare_turn(
            conversation_id=conversation_id,
            image_content=image_content,
            image_content_type=image_content_type,
            audio_content=audio_content,
            audio_filename=audio_filename,
            audio_content_type=audio_content_type,
            language=language,
            telemetry=telemetry,
            optimize_for_stream=False,
            request_id=request_id,
        )
        speech = await self._pipeline.synthesize(prepared)
        return MultimodalTurnResult(speech=speech, message_id=prepared.message_id)

    async def stream_turn(
        self,
        conversation_id: UUID,
        *,
        image_content: bytes,
        image_content_type: str,
        audio_content: bytes,
        audio_filename: str,
        audio_content_type: str,
        language: str = "ru",
        recording_duration_ms: int | None = None,
        request_id: UUID | None = None,
    ) -> AsyncIterator[bytes]:
        """Yield cancellable Voice 2.0 events for one spoken-image question."""

        telemetry = VoiceTurnTelemetry(
            metrics=self._metrics,
            mode="multimodal",
            recording_duration_ms=recording_duration_ms,
            streamed=True,
        )
        request_id = request_trace_registry.request_id(request_id)
        voice_stream_registry.register(telemetry.turn_id)
        yield encode_stream_event("started", turn_id=str(telemetry.turn_id))
        try:
            prepared = await self._prepare_turn(
                conversation_id=conversation_id,
                image_content=image_content,
                image_content_type=image_content_type,
                audio_content=audio_content,
                audio_filename=audio_filename,
                audio_content_type=audio_content_type,
                language=language,
                telemetry=telemetry,
                optimize_for_stream=True,
                request_id=request_id,
            )
            async for event in self._pipeline.stream_synthesis(prepared):
                yield event
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
        except ImageUnderstandingNotAllowedError:
            request_trace_registry.finish(request_id, "error", error_code="vision_not_allowed")
            yield encode_stream_event(
                "error",
                code="image_not_allowed",
                message="Этот персонаж пока не умеет рассматривать фотографии.",
            )
        except (InvalidImageError, ImageUnderstandingUnavailableError):
            request_trace_registry.finish(request_id, "error", error_code="vision")
            yield encode_stream_event(
                "error",
                code="vision_unavailable",
                message="Сейчас я не могу рассмотреть фотографию. Попробуем позже.",
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
            logger.exception("streaming_multimodal_turn_failed")
            request_trace_registry.finish(request_id, "error", error_code="provider_error")
            yield encode_stream_event(
                "error",
                code="provider_unavailable",
                message="Не получилось подготовить ответ. Давай попробуем ещё раз.",
            )
        finally:
            voice_stream_registry.unregister(telemetry.turn_id)

    async def _prepare_turn(
        self,
        *,
        conversation_id: UUID,
        image_content: bytes,
        image_content_type: str,
        audio_content: bytes,
        audio_filename: str,
        audio_content_type: str,
        language: str,
        telemetry: VoiceTurnTelemetry,
        optimize_for_stream: bool,
        request_id: UUID,
    ) -> PreparedVoiceResponse:
        error_stage = "stt_vision"
        diagnostics = TurnDiagnostics()
        try:
            self._image_understanding.ensure_allowed(conversation_id)
            active_agent = self._conversation.get_conversation_agent(conversation_id)

            async def inspect() -> EphemeralImageObservations:
                started_at = time.perf_counter()
                try:
                    return await self._image_understanding.inspect(
                        conversation_id,
                        question=NEUTRAL_VISUAL_QUESTION,
                        image_content=image_content,
                        content_type=image_content_type,
                        request_id=request_id,
                    )
                finally:
                    telemetry.vision_duration_ms = round((time.perf_counter() - started_at) * 1000)

            transcription_result, observations_result = await asyncio.gather(
                self._pipeline.transcribe(
                    TranscriptionRequest(
                        audio_content=audio_content,
                        filename=audio_filename,
                        content_type=audio_content_type,
                        language=language,
                        request_id=request_id,
                    ),
                    telemetry,
                    request_id,
                ),
                inspect(),
                return_exceptions=True,
            )
            if isinstance(transcription_result, BaseException):
                error_stage = "stt"
                raise transcription_result
            if isinstance(observations_result, BaseException):
                error_stage = "vision"
                raise observations_result

            telemetry.stt_confidence = transcription_result.confidence
            telemetry.recording_duration_ms = (
                transcription_result.duration_ms or telemetry.recording_duration_ms
            )
            transcript = transcription_result.text.strip()
            if not transcript:
                error_stage = "stt"
                raise VoiceInputError("Audio did not contain recognizable speech")
            logger.info(
                "multimodal_inputs_completed",
                extra={
                    "transcript_characters": len(transcript),
                    "observation_characters": len(observations_result.description),
                    "confidence": telemetry.stt_confidence,
                    "recording_duration_ms": telemetry.recording_duration_ms,
                },
            )

            error_stage = "llm"
            request_trace_registry.event(request_id, "llm", "started")
            ai_message = await run_with_stage_timeout(
                self._conversation.process_turn(
                    conversation_id,
                    transcript,
                    runtime_context=combine_runtime_context(
                        observations_result.prompt_context,
                        VOICE_RESPONSE_CONTEXT if optimize_for_stream else None,
                    ),
                    input_safety_context=observations_result.description,
                    diagnostics=diagnostics,
                    request_id=request_id,
                ),
                seconds=self._execution_policy.llm_timeout_seconds,
                stage="llm",
            )
            telemetry.llm_duration_ms = diagnostics.llm_duration_ms
            request_trace_registry.event(
                request_id, "llm", "success", duration_ms=telemetry.llm_duration_ms
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
                error_stage=error_stage,
                cancelled=True,
            )
            raise
        except Exception as exc:
            telemetry.llm_duration_ms = diagnostics.llm_duration_ms
            telemetry.record(status="error", error_stage=error_stage)
            if error_stage == "llm":
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
