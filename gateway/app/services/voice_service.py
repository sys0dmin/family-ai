"""Application service for a complete voice conversation turn."""

import asyncio
import logging
from uuid import UUID

from gateway.app.providers.base import AIProvider
from gateway.app.providers.schemas import (
    SpeechRequest,
    SpeechResponse,
    TranscriptionRequest,
)
from gateway.app.services.conversation_service import ConversationService
from gateway.app.services.music_recognition_service import MusicRecognitionService

logger = logging.getLogger(__name__)


class VoiceInputError(ValueError):
    """Raised when a recording cannot produce a useful transcript."""


class VoiceService:
    """Coordinate STT, the safe conversation flow, and TTS."""

    def __init__(
        self,
        ai_provider: AIProvider,
        conversation_service: ConversationService,
        music_recognition_service: MusicRecognitionService | None = None,
    ) -> None:
        self._ai_provider = ai_provider
        self._conversation_service = conversation_service
        self._music_recognition_service = music_recognition_service

    async def process_voice_turn(
        self,
        conversation_id: UUID,
        audio_content: bytes,
        filename: str,
        content_type: str,
        language: str = "ru",
    ) -> SpeechResponse:
        """Run one audio request through STT, conversation safety, and TTS."""

        active_agent = self._conversation_service.get_conversation_agent(conversation_id)
        transcription_request = TranscriptionRequest(
            audio_content=audio_content,
            filename=filename,
            content_type=content_type,
            language=language,
        )
        recognition_task = None
        if self._music_recognition_service is not None:
            recognition_task = self._music_recognition_service.recognize_for_agent(
                agent=active_agent,
                audio_content=audio_content,
                filename=filename,
                content_type=content_type,
            )
        if recognition_task is None:
            transcription = await self._ai_provider.transcribe_audio(transcription_request)
            recognition = None
        else:
            transcription, recognition = await asyncio.gather(
                self._ai_provider.transcribe_audio(transcription_request),
                recognition_task,
            )
        transcript = transcription.text.strip()
        if not transcript and recognition is None:
            raise VoiceInputError("Audio did not contain recognizable speech")
        if not transcript:
            transcript = "[Лера напела мелодию без слов]"

        logger.info(
            "voice_transcription_completed",
            extra={"transcript_characters": len(transcript)},
        )

        ai_message = await self._conversation_service.process_turn(
            conversation_id=conversation_id,
            text=transcript,
            runtime_context=recognition.prompt_context if recognition else None,
        )
        speech = await self._ai_provider.synthesize_speech(
            SpeechRequest(text=ai_message.content, voice=active_agent.tts_voice)
        )
        logger.info(
            "voice_synthesis_completed",
            extra={"audio_bytes": len(speech.audio_content)},
        )
        return speech

    async def synthesize_text(
        self,
        conversation_id: UUID,
        text: str,
    ) -> SpeechResponse:
        """Speak existing assistant text with the agent bound to the conversation."""

        active_agent = self._conversation_service.get_conversation_agent(conversation_id)
        return await self._ai_provider.synthesize_speech(
            SpeechRequest(text=text.strip(), voice=active_agent.tts_voice)
        )
