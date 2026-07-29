"""Application orchestration for one spoken question about one image."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

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
from gateway.app.services.image_understanding_service import (
    EphemeralImageObservations,
    ImageUnderstandingNotAllowedError,
    ImageUnderstandingService,
    ImageUnderstandingUnavailableError,
    InvalidImageError,
)
from gateway.app.services.turn_diagnostics import TurnDiagnostics
from gateway.app.services.voice_service import VoiceInputError
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
    ) -> None:
        self._recognition_provider = recognition_provider
        self._synthesis_provider = synthesis_provider
        self._image_understanding = image_understanding
        self._conversation = conversation
        self._metrics = metrics

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
    ) -> MultimodalTurnResult:
        telemetry = VoiceTurnTelemetry(
            metrics=self._metrics,
            mode="multimodal",
            recording_duration_ms=recording_duration_ms,
            streamed=False,
        )
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
        )
        tts_started_at = time.perf_counter()
        try:
            speech = await self._synthesis_provider.synthesize_speech(
                SpeechRequest(text=prepared.text, voice=prepared.voice)
            )
        except Exception:
            telemetry.tts_duration_ms = round(
                (time.perf_counter() - tts_started_at) * 1000
            )
            telemetry.record(status="error", error_stage="tts")
            raise
        finally:
            telemetry.tts_duration_ms = round(
                (time.perf_counter() - tts_started_at) * 1000
            )
        telemetry.record(status="success")
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
    ) -> AsyncIterator[bytes]:
        """Yield cancellable Voice 2.0 events for one spoken-image question."""

        telemetry = VoiceTurnTelemetry(
            metrics=self._metrics,
            mode="multimodal",
            recording_duration_ms=recording_duration_ms,
            streamed=True,
        )
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
            )
            async for event in stream_speech_events(
                prepared,
                self._synthesis_provider,
            ):
                yield event
        except asyncio.CancelledError:
            telemetry.record(
                status="cancelled",
                error_stage="cancelled",
                cancelled=True,
            )
            raise
        except VoiceInputError:
            yield encode_stream_event(
                "error",
                code="speech_not_recognized",
                message="Не удалось расслышать вопрос. Попробуем ещё раз.",
            )
        except ImageUnderstandingNotAllowedError:
            yield encode_stream_event(
                "error",
                code="image_not_allowed",
                message="Этот персонаж пока не умеет рассматривать фотографии.",
            )
        except (InvalidImageError, ImageUnderstandingUnavailableError):
            yield encode_stream_event(
                "error",
                code="vision_unavailable",
                message="Сейчас я не могу рассмотреть фотографию. Попробуем позже.",
            )
        except Exception:
            telemetry.record(status="error", error_stage="tts")
            logger.exception("streaming_multimodal_turn_failed")
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
    ) -> PreparedVoiceResponse:
        error_stage = "stt_vision"
        diagnostics = TurnDiagnostics()
        try:
            self._image_understanding.ensure_allowed(conversation_id)
            active_agent = self._conversation.get_conversation_agent(conversation_id)

            async def transcribe() -> TranscriptionResponse:
                started_at = time.perf_counter()
                try:
                    return await self._recognition_provider.transcribe_audio(
                        TranscriptionRequest(
                            audio_content=audio_content,
                            filename=audio_filename,
                            content_type=audio_content_type,
                            language=language,
                        )
                    )
                finally:
                    telemetry.stt_duration_ms = round(
                        (time.perf_counter() - started_at) * 1000
                    )

            async def inspect() -> EphemeralImageObservations:
                started_at = time.perf_counter()
                try:
                    return await self._image_understanding.inspect(
                        conversation_id,
                        question=NEUTRAL_VISUAL_QUESTION,
                        image_content=image_content,
                        content_type=image_content_type,
                    )
                finally:
                    telemetry.vision_duration_ms = round(
                        (time.perf_counter() - started_at) * 1000
                    )

            transcription_result, observations_result = await asyncio.gather(
                transcribe(),
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
            ai_message = await self._conversation.process_turn(
                conversation_id,
                transcript,
                runtime_context=combine_runtime_context(
                    observations_result.prompt_context,
                    VOICE_RESPONSE_CONTEXT if optimize_for_stream else None,
                ),
                input_safety_context=observations_result.description,
                diagnostics=diagnostics,
            )
            telemetry.llm_duration_ms = diagnostics.llm_duration_ms
            return PreparedVoiceResponse(
                message_id=ai_message.id,
                text=ai_message.content,
                voice=active_agent.tts_voice,
                telemetry=telemetry,
            )
        except asyncio.CancelledError:
            telemetry.record(
                status="cancelled",
                error_stage=error_stage,
                cancelled=True,
            )
            raise
        except Exception:
            telemetry.llm_duration_ms = diagnostics.llm_duration_ms
            telemetry.record(status="error", error_stage=error_stage)
            raise
