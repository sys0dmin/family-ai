"""Application service for a complete voice conversation turn."""

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
from gateway.app.services.music_recognition_service import MusicRecognitionService
from gateway.app.services.turn_diagnostics import TurnDiagnostics

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

        total_started_at = time.perf_counter()
        stage = "stt"
        stt_duration_ms: int | None = None
        tts_duration_ms: int | None = None
        stt_confidence: float | None = None
        diagnostics = TurnDiagnostics()

        active_agent = self._conversation_service.get_conversation_agent(conversation_id)
        transcription_request = TranscriptionRequest(
            audio_content=audio_content,
            filename=filename,
            content_type=content_type,
            language=language,
        )

        async def transcribe() -> TranscriptionResponse:
            nonlocal stt_duration_ms
            started_at = time.perf_counter()
            try:
                return await self._recognition_provider.transcribe_audio(
                    transcription_request
                )
            finally:
                stt_duration_ms = round((time.perf_counter() - started_at) * 1000)

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

            stt_confidence = transcription.confidence
            recording_duration_ms = transcription.duration_ms or recording_duration_ms
            transcript = transcription.text.strip()
            if not transcript and recognition is None:
                raise VoiceInputError("Audio did not contain recognizable speech")
            if not transcript:
                transcript = "[Лера напела мелодию без слов]"

            logger.info(
                "voice_transcription_completed",
                extra={
                    "transcript_characters": len(transcript),
                    "confidence": stt_confidence,
                    "recording_duration_ms": recording_duration_ms,
                },
            )

            stage = "llm"
            ai_message = await self._conversation_service.process_turn(
                conversation_id=conversation_id,
                text=transcript,
                runtime_context=recognition.prompt_context if recognition else None,
                diagnostics=diagnostics,
            )
            stage = "tts"
            tts_started_at = time.perf_counter()
            try:
                speech = await self._synthesis_provider.synthesize_speech(
                    SpeechRequest(text=ai_message.content, voice=active_agent.tts_voice)
                )
            finally:
                tts_duration_ms = round((time.perf_counter() - tts_started_at) * 1000)
            logger.info(
                "voice_synthesis_completed",
                extra={"audio_bytes": len(speech.audio_content)},
            )
        except Exception:
            self._record_metrics(
                status="error",
                error_stage=stage,
                started_at=total_started_at,
                recording_duration_ms=recording_duration_ms,
                stt_duration_ms=stt_duration_ms,
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
            llm_duration_ms=diagnostics.llm_duration_ms,
            tts_duration_ms=tts_duration_ms,
            stt_confidence=stt_confidence,
        )
        return VoiceTurnResult(speech=speech, message_id=ai_message.id)

    def _record_metrics(
        self,
        *,
        status: str,
        error_stage: str | None,
        started_at: float,
        recording_duration_ms: int | None,
        stt_duration_ms: int | None,
        llm_duration_ms: int | None,
        tts_duration_ms: int | None,
        stt_confidence: float | None,
    ) -> None:
        self._metrics.record(
            status=status,
            mode="voice",
            error_stage=error_stage,
            recording_duration_ms=recording_duration_ms,
            stt_duration_ms=stt_duration_ms,
            llm_duration_ms=llm_duration_ms,
            tts_duration_ms=tts_duration_ms,
            total_duration_ms=round((time.perf_counter() - started_at) * 1000),
            stt_confidence=stt_confidence,
        )

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
