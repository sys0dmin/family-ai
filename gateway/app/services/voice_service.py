import logging
from typing import Optional
from uuid import UUID

from gateway.app.providers.base import AIProvider
from gateway.app.providers.schemas import SpeechRequest, TranscriptionRequest
from gateway.app.services.conversation_service import ConversationService

logger = logging.getLogger(__name__)

class VoiceService:
    def __init__(
        self, 
        ai_provider: AIProvider, 
        conversation_service: ConversationService
    ):
        self.ai_provider = ai_provider
        self.conversation_service = conversation_service

    async def process_voice_turn(
        self, 
        conversation_id: UUID, 
        audio_content: bytes,
        extension: str = "wav"
    ) -> Optional[bytes]:
        """
        Полный цикл: Голос -> Текст -> Ответ ИИ -> Голос.
        """
        # 1. STT: Распознаем речь
        transcription = await self.ai_provider.transcribe(
            TranscriptionRequest(audio_content=audio_content, extension=extension)
        )
        
        if not transcription.text:
            logger.warning("Не удалось распознать аудио")
            return None

        logger.info(f"Распознанный текст: {transcription.text}")

        # 2. Логика диалога: сохранение, безопасность и генерация ответа
        ai_message = await self.conversation_service.process_turn(
            conversation_id=conversation_id,
            text=transcription.text
        )

        # 3. TTS: Синтезируем голос ассистента
        speech = await self.ai_provider.text_to_speech(
            SpeechRequest(text=ai_message.content)
        )

        return speech.audio_content
