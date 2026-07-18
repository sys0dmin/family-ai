"""FastAPI dependencies for the Gateway."""

from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from gateway.app.agents import SqlAlchemyAgentRepository
from gateway.app.config import Settings
from gateway.app.db.session import get_db_session
from gateway.app.providers.base import AIProvider
from gateway.app.providers.openai import OpenAIProvider
from gateway.app.services.agent_service import AgentService
from gateway.app.services.conversation_service import ConversationService
from gateway.app.services.safety_service import SafetyService
from gateway.app.services.voice_service import VoiceService


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
    )


def get_agent_service(
    session: Session = Depends(get_db_session),
) -> AgentService:
    """Return agent business rules backed by the configured database."""

    return AgentService(SqlAlchemyAgentRepository(session))


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
) -> VoiceService:
    """Return a voice service with injected dependencies."""
    return VoiceService(provider, conversation)
