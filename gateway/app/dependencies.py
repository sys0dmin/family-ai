"""FastAPI dependencies for the Gateway."""

from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from gateway.app.config import get_settings
from gateway.app.db.session import get_db_session
from gateway.app.providers.base import AIProvider
from gateway.app.providers.openai import OpenAIProvider
from gateway.app.services.conversation_service import ConversationService


def get_ai_provider() -> AIProvider:
    """Return the configured AI provider singleton."""
    settings = get_settings()
    return OpenAIProvider(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
    )


def get_conversation_service(
    session: Session = Depends(get_db_session),
    provider: AIProvider = Depends(get_ai_provider),
) -> ConversationService:
    """Return a conversation service with injected dependencies."""
    return ConversationService(session, provider)
