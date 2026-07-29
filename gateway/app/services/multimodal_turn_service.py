"""Application orchestration for one spoken question about one image."""

import asyncio
import logging
import time
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
    ImageUnderstandingService,
)
from gateway.app.services.turn_diagnostics import TurnDiagnostics
from gateway.app.services.voice_service import VoiceInputError

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
        total_started_at = time.perf_counter()
        error_stage = "stt_vision"
        stt_duration_ms: int | None = None
        vision_duration_ms: int | None = None
        tts_duration_ms: int | None = None
        stt_confidence: float | None = None
        diagnostics = TurnDiagnostics()
        self._image_understanding.ensure_allowed(conversation_id)
        active_agent = self._conversation.get_conversation_agent(conversation_id)

        async def transcribe() -> TranscriptionResponse:
            nonlocal stt_duration_ms
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
                stt_duration_ms = round((time.perf_counter() - started_at) * 1000)

        async def inspect() -> EphemeralImageObservations:
            nonlocal vision_duration_ms
            started_at = time.perf_counter()
            try:
                return await self._image_understanding.inspect(
                    conversation_id,
                    question=NEUTRAL_VISUAL_QUESTION,
                    image_content=image_content,
                    content_type=image_content_type,
                )
            finally:
                vision_duration_ms = round((time.perf_counter() - started_at) * 1000)

        try:
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

            stt_confidence = transcription_result.confidence
            recording_duration_ms = (
                transcription_result.duration_ms or recording_duration_ms
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
                    "confidence": stt_confidence,
                    "recording_duration_ms": recording_duration_ms,
                },
            )

            error_stage = "llm"
            ai_message = await self._conversation.process_turn(
                conversation_id,
                transcript,
                runtime_context=observations_result.prompt_context,
                input_safety_context=observations_result.description,
                diagnostics=diagnostics,
            )
            error_stage = "tts"
            tts_started_at = time.perf_counter()
            try:
                speech = await self._synthesis_provider.synthesize_speech(
                    SpeechRequest(
                        text=ai_message.content,
                        voice=active_agent.tts_voice,
                    )
                )
            finally:
                tts_duration_ms = round((time.perf_counter() - tts_started_at) * 1000)
        except Exception:
            self._record_metrics(
                status="error",
                error_stage=error_stage,
                started_at=total_started_at,
                recording_duration_ms=recording_duration_ms,
                stt_duration_ms=stt_duration_ms,
                vision_duration_ms=vision_duration_ms,
                llm_duration_ms=diagnostics.llm_duration_ms,
                tts_duration_ms=tts_duration_ms,
                stt_confidence=stt_confidence,
            )
            raise

        self._record_metrics(
            status="success",
            error_stage=None,
            started_at=total_started_at,
            recording_duration_ms=recording_duration_ms,
            stt_duration_ms=stt_duration_ms,
            vision_duration_ms=vision_duration_ms,
            llm_duration_ms=diagnostics.llm_duration_ms,
            tts_duration_ms=tts_duration_ms,
            stt_confidence=stt_confidence,
        )
        return MultimodalTurnResult(speech=speech, message_id=ai_message.id)

    def _record_metrics(
        self,
        *,
        status: str,
        error_stage: str | None,
        started_at: float,
        recording_duration_ms: int | None,
        stt_duration_ms: int | None,
        vision_duration_ms: int | None,
        llm_duration_ms: int | None,
        tts_duration_ms: int | None,
        stt_confidence: float | None,
    ) -> None:
        self._metrics.record(
            mode="multimodal",
            status=status,
            error_stage=error_stage,
            recording_duration_ms=recording_duration_ms,
            stt_duration_ms=stt_duration_ms,
            vision_duration_ms=vision_duration_ms,
            llm_duration_ms=llm_duration_ms,
            tts_duration_ms=tts_duration_ms,
            total_duration_ms=round((time.perf_counter() - started_at) * 1000),
            stt_confidence=stt_confidence,
        )
