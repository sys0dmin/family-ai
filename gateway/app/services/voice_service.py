"""Application service for a complete voice conversation turn."""

import logging
from uuid import UUID

from gateway.app.providers.base import AIProvider
from gateway.app.providers.schemas import (
    SpeechRequest,
    SpeechResponse,
    TranscriptionRequest,
)
from gateway.app.services.conversation_service import ConversationService

logger = logging.getLogger(__name__)


class VoiceInputError(ValueError):
    """Raised when a recording cannot produce a useful transcript."""


class VoiceService:
    """Coordinate STT, the safe conversation flow, and TTS."""

    def __init__(
        self,
        ai_provider: AIProvider,
        conversation_service: ConversationService,
    ) -> None:
        self._ai_provider = ai_provider
        self._conversation_service = conversation_service

    async def process_voice_turn(
        self,
        conversation_id: UUID,
        audio_content: bytes,
        filename: str,
        content_type: str,
        language: str = "ru",
    ) -> SpeechResponse:
        """Run one audio request through STT, conversation safety, and TTS."""

        transcription = await self._ai_provider.transcribe_audio(
            TranscriptionRequest(
                audio_content=audio_content,
                filename=filename,
                content_type=content_type,
                language=language,
            )
        )
        transcript = transcription.text.strip()
        if not transcript:
            raise VoiceInputError("Audio did not contain recognizable speech")

        logger.info(
            "voice_transcription_completed",
            extra={"transcript_characters": len(transcript)},
        )

        ai_message = await self._conversation_service.process_turn(
            conversation_id=conversation_id,
            text=transcript,
        )
        speech = await self._ai_provider.synthesize_speech(
            SpeechRequest(text=ai_message.content)
        )
        logger.info(
            "voice_synthesis_completed",
            extra={"audio_bytes": len(speech.audio_content)},
        )
        return speech
