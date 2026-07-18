"""FastAPI dependencies for the Gateway."""

import logging
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from gateway.app.agents import SqlAlchemyAgentRepository
from gateway.app.config import Settings
from gateway.app.db.session import get_db_session
from gateway.app.music import MusicRecognitionProvider
from gateway.app.music.acrcloud import AcrCloudMusicRecognitionProvider
from gateway.app.providers.base import AIProvider
from gateway.app.providers.openai import OpenAIProvider
from gateway.app.services.agent_service import AgentService
from gateway.app.services.conversation_service import ConversationService
from gateway.app.services.music_recognition_service import MusicRecognitionService
from gateway.app.services.safety_service import SafetyService
from gateway.app.services.voice_service import VoiceService

logger = logging.getLogger(__name__)


@lru_cache
def get_safety_service() -> SafetyService:
    """Return the safety service singleton."""
    return SafetyService()


def get_ai_provider() -> AIProvider:
    """Return provider configuration loaded from the latest .env values."""
    settings = Settings()
    return OpenAIProvider(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
        base_url=settings.openai_base_url,
        speech_api_key=settings.speech_api_key.get_secret_value() or None,
        speech_base_url=settings.speech_base_url,
        stt_model=settings.stt_model,
        stt_temperature=settings.stt_temperature,
        tts_model=settings.tts_model,
        tts_voice=settings.tts_voice,
        tts_response_format=settings.tts_response_format,
        web_search_tool_type=settings.web_search_tool_type,
    )


def get_agent_service(
    session: Session = Depends(get_db_session),
) -> AgentService:
    """Return agent business rules backed by the configured database."""

    return AgentService(SqlAlchemyAgentRepository(session))


def get_music_recognition_provider() -> MusicRecognitionProvider | None:
    """Build the configured optional melody recognition provider."""

    settings = Settings()
    if settings.music_recognition_provider == "disabled":
        return None
    host = (settings.acrcloud_host or "").strip()
    access_key = settings.acrcloud_access_key.get_secret_value().strip()
    access_secret = settings.acrcloud_access_secret.get_secret_value().strip()
    if not host or not access_key or not access_secret:
        return None
    try:
        return AcrCloudMusicRecognitionProvider(
            host=host,
            access_key=access_key,
            access_secret=access_secret,
            timeout_seconds=settings.music_recognition_timeout_seconds,
        )
    except ValueError:
        logger.warning("music_recognition_provider_configuration_invalid")
        return None


def get_music_recognition_service(
    provider: MusicRecognitionProvider | None = Depends(get_music_recognition_provider),
) -> MusicRecognitionService:
    return MusicRecognitionService(provider)


def get_conversation_service(
    session: Session = Depends(get_db_session),
    provider: AIProvider = Depends(get_ai_provider),
    safety: SafetyService = Depends(get_safety_service),
    agents: AgentService = Depends(get_agent_service),
) -> ConversationService:
    """Return a conversation service with injected dependencies."""
    settings = Settings()
    return ConversationService(
        session,
        provider,
        safety,
        agents,
        default_agent_id=settings.default_agent_id,
    )


def get_voice_service(
    provider: AIProvider = Depends(get_ai_provider),
    conversation: ConversationService = Depends(get_conversation_service),
    music_recognition: MusicRecognitionService = Depends(get_music_recognition_service),
) -> VoiceService:
    """Return a voice service with injected dependencies."""
    return VoiceService(provider, conversation, music_recognition)
