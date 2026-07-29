"""Application service for a complete voice conversation turn."""

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
from gateway.app.services.music_recognition_service import MusicRecognitionService
from gateway.app.services.turn_diagnostics import TurnDiagnostics
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
    ) -> None:
        self._recognition_provider = recognition_provider
        self._synthesis_provider = synthesis_provider
        self._conversation_service = conversation_service
        self._music_recognition_service = music_recognition_service
        self._metrics = metrics or VoiceMetricsRegistry()

    async def process_voice_turn(
        self,
        conversation_id: UUID,
        audio_content: bytes,
        filename: str,
        content_type: str,
        language: str = "ru",
        recording_duration_ms: int | None = None,
    ) -> VoiceTurnResult:
        """Run one audio request through STT, conversation safety, and TTS."""

        telemetry = VoiceTurnTelemetry(
            metrics=self._metrics,
            mode="voice",
            recording_duration_ms=recording_duration_ms,
            streamed=False,
        )
        prepared = await self._prepare_voice_turn(
            conversation_id=conversation_id,
            audio_content=audio_content,
            filename=filename,
            content_type=content_type,
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
    ) -> AsyncIterator[bytes]:
        """Yield NDJSON events and stop remaining work when the turn is cancelled."""

        telemetry = VoiceTurnTelemetry(
            metrics=self._metrics,
            mode="voice",
            recording_duration_ms=recording_duration_ms,
            streamed=True,
        )
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
        except Exception:
            telemetry.record(status="error", error_stage="tts")
            logger.exception("streaming_voice_turn_failed")
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
    ) -> PreparedVoiceResponse:
        stage = "stt"
        diagnostics = TurnDiagnostics()
        active_agent = self._conversation_service.get_conversation_agent(conversation_id)
        transcription_request = TranscriptionRequest(
            audio_content=audio_content,
            filename=filename,
            content_type=content_type,
            language=language,
        )

        async def transcribe() -> TranscriptionResponse:
            started_at = time.perf_counter()
            try:
                return await self._recognition_provider.transcribe_audio(
                    transcription_request
                )
            finally:
                telemetry.stt_duration_ms = round(
                    (time.perf_counter() - started_at) * 1000
                )

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
            ai_message = await self._conversation_service.process_turn(
                conversation_id=conversation_id,
                text=transcript,
                runtime_context=combine_runtime_context(
                    recognition.prompt_context if recognition else None,
                    VOICE_RESPONSE_CONTEXT if optimize_for_stream else None,
                ),
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
                error_stage=stage,
                cancelled=True,
            )
            raise
        except Exception:
            telemetry.llm_duration_ms = diagnostics.llm_duration_ms
            telemetry.record(status="error", error_stage=stage)
            raise

    async def synthesize_text(
        self,
        conversation_id: UUID,
        text: str,
    ) -> SpeechResponse:
        """Speak existing assistant text with the agent bound to the conversation."""

        active_agent = self._conversation_service.get_conversation_agent(conversation_id)
        return await self._synthesis_provider.synthesize_speech(
            SpeechRequest(text=text.strip(), voice=active_agent.tts_voice)
        )
