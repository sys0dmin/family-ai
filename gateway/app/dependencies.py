"""FastAPI dependencies for the Gateway."""

import logging
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from gateway.app.activities import ActivityCatalog, ActivityService
from gateway.app.agents import SqlAlchemyAgentRepository
from gateway.app.calibration.service import SpeechCalibrationService
from gateway.app.config import Settings, get_settings
from gateway.app.db.session import get_db_session
from gateway.app.images import ImageSearchProvider, OpenverseImageSearchProvider
from gateway.app.memory import MemoryService, SqlAlchemyMemoryRepository
from gateway.app.music import MusicRecognitionProvider
from gateway.app.music.acrcloud import AcrCloudMusicRecognitionProvider
from gateway.app.observability.voice_metrics import voice_metrics_registry
from gateway.app.providers.base import AIProvider
from gateway.app.providers.contracts import (
    ChatProvider,
    ImageUnderstandingProvider,
    SpeechRecognitionProvider,
    SpeechSynthesisProvider,
)
from gateway.app.providers.openai import OpenAIProvider
from gateway.app.providers.openai_chat import OpenAIChatProvider
from gateway.app.providers.openai_stt import OpenAISpeechRecognitionProvider
from gateway.app.providers.openai_tts import OpenAISpeechSynthesisProvider
from gateway.app.providers.openai_vision import OpenAIImageUnderstandingProvider
from gateway.app.safety.engine import SafetyPolicyEngine
from gateway.app.safety.metrics import safety_metrics_registry
from gateway.app.services.agent_service import AgentService
from gateway.app.services.conversation_service import ConversationService
from gateway.app.services.image_understanding_service import ImageUnderstandingService
from gateway.app.services.multimodal_turn_service import MultimodalTurnService
from gateway.app.services.music_recognition_service import MusicRecognitionService
from gateway.app.services.safety_service import SafetyService
from gateway.app.services.visual_media_service import VisualMediaService
from gateway.app.services.voice_service import VoiceService
from gateway.app.speech_runtime.service import SpeechRuntimeService

logger = logging.getLogger(__name__)


@lru_cache
def get_safety_service() -> SafetyService:
    """Return the safety service singleton."""
    return SafetyService(SafetyPolicyEngine(safety_metrics_registry))


def get_ai_provider() -> AIProvider:
    """Return the deprecated composite provider for compatibility callers."""
    settings = Settings()
    return OpenAIProvider(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
        base_url=settings.openai_base_url,
        speech_api_key=settings.speech_api_key.get_secret_value() or None,
        speech_base_url=settings.speech_base_url,
        stt_model=settings.stt_model,
        stt_temperature=settings.stt_temperature,
        stt_initial_prompt=settings.stt_initial_prompt,
        tts_model=settings.tts_model,
        tts_voice=settings.tts_voice,
        tts_response_format=settings.tts_response_format,
        web_search_tool_type=settings.web_search_tool_type,
    )


def get_chat_provider() -> ChatProvider:
    """Build only the configured language-model adapter."""

    settings = Settings()
    return OpenAIChatProvider(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
        base_url=settings.openai_base_url,
        web_search_tool_type=settings.web_search_tool_type,
    )


def get_speech_recognition_provider() -> SpeechRecognitionProvider:
    """Build the STT adapter independently from chat and TTS."""

    settings = Settings()
    api_key = (
        settings.stt_api_key.get_secret_value()
        or settings.speech_api_key.get_secret_value()
        or settings.openai_api_key.get_secret_value()
    )
    return OpenAISpeechRecognitionProvider(
        api_key=api_key,
        model=settings.stt_model,
        base_url=(
            settings.stt_base_url
            or settings.speech_base_url
            or settings.openai_base_url
        ),
        temperature=settings.stt_temperature,
        initial_prompt=settings.stt_initial_prompt,
    )


def get_speech_synthesis_provider() -> SpeechSynthesisProvider:
    """Build the TTS adapter independently from chat and STT."""

    settings = Settings()
    api_key = (
        settings.tts_api_key.get_secret_value()
        or settings.speech_api_key.get_secret_value()
        or settings.openai_api_key.get_secret_value()
    )
    return OpenAISpeechSynthesisProvider(
        api_key=api_key,
        model=settings.tts_model,
        base_url=(
            settings.tts_base_url
            or settings.speech_base_url
            or settings.openai_base_url
        ),
        default_voice=settings.tts_voice,
        response_format=settings.tts_response_format,
    )


def get_speech_calibration_service(
    settings: Settings = Depends(get_settings),
) -> SpeechCalibrationService:
    return SpeechCalibrationService(settings)


def get_speech_runtime_service(
    settings: Settings = Depends(get_settings),
) -> SpeechRuntimeService:
    return SpeechRuntimeService(settings)


def get_agent_service(
    session: Session = Depends(get_db_session),
) -> AgentService:
    """Return agent business rules backed by the configured database."""

    return AgentService(SqlAlchemyAgentRepository(session))


def get_memory_service(
    session: Session = Depends(get_db_session),
) -> MemoryService:
    """Return the provider-independent durable memory domain."""

    return MemoryService(SqlAlchemyMemoryRepository(session))


def get_activity_service(
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ActivityService:
    return ActivityService(
        session,
        ActivityCatalog(),
        retention_hours=settings.activity_retention_hours,
    )


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
    safety: SafetyService = Depends(get_safety_service),
) -> MusicRecognitionService:
    return MusicRecognitionService(provider, safety)


def get_image_search_provider() -> ImageSearchProvider | None:
    """Build the optional licensed-image provider."""

    settings = Settings()
    if settings.image_search_provider == "disabled":
        return None
    return OpenverseImageSearchProvider(settings.image_search_timeout_seconds)


def get_image_understanding_provider() -> ImageUnderstandingProvider | None:
    """Build the optional vision adapter independently from the chat model."""

    settings = Settings()
    if settings.vision_provider == "disabled":
        return None
    api_key = (
        settings.vision_api_key.get_secret_value()
        or settings.openai_api_key.get_secret_value()
    )
    return OpenAIImageUnderstandingProvider(
        api_key=api_key,
        model=settings.vision_model,
        base_url=settings.vision_base_url or settings.openai_base_url,
    )


def get_visual_media_service(
    session: Session = Depends(get_db_session),
    provider: ImageSearchProvider | None = Depends(get_image_search_provider),
    safety: SafetyService = Depends(get_safety_service),
) -> VisualMediaService:
    settings = Settings()
    return VisualMediaService(
        session,
        provider,
        settings.image_search_timeout_seconds,
        safety,
    )


def get_conversation_service(
    session: Session = Depends(get_db_session),
    provider: ChatProvider = Depends(get_chat_provider),
    safety: SafetyService = Depends(get_safety_service),
    agents: AgentService = Depends(get_agent_service),
    visual_media: VisualMediaService = Depends(get_visual_media_service),
    memory: MemoryService = Depends(get_memory_service),
    activities: ActivityService = Depends(get_activity_service),
    settings: Settings = Depends(get_settings),
) -> ConversationService:
    """Return a conversation service with injected dependencies."""
    return ConversationService(
        session,
        provider,
        safety,
        agents,
        visual_media,
        default_agent_id=settings.default_agent_id,
        retention_days=settings.message_retention_days,
        memory=memory,
        activities=activities,
    )


def get_image_understanding_service(
    provider: ImageUnderstandingProvider | None = Depends(
        get_image_understanding_provider
    ),
    conversation: ConversationService = Depends(get_conversation_service),
    safety: SafetyService = Depends(get_safety_service),
    settings: Settings = Depends(get_settings),
) -> ImageUnderstandingService:
    """Return the application service for ephemeral child-image turns."""

    return ImageUnderstandingService(
        provider=provider,
        conversation=conversation,
        safety=safety,
        max_image_bytes=settings.vision_max_image_bytes,
    )


def get_voice_service(
    recognition: SpeechRecognitionProvider = Depends(
        get_speech_recognition_provider
    ),
    synthesis: SpeechSynthesisProvider = Depends(get_speech_synthesis_provider),
    conversation: ConversationService = Depends(get_conversation_service),
    music_recognition: MusicRecognitionService = Depends(get_music_recognition_service),
) -> VoiceService:
    """Return a voice service with injected dependencies."""
    return VoiceService(
        recognition,
        synthesis,
        conversation,
        music_recognition,
        metrics=voice_metrics_registry,
    )


def get_multimodal_turn_service(
    recognition: SpeechRecognitionProvider = Depends(
        get_speech_recognition_provider
    ),
    synthesis: SpeechSynthesisProvider = Depends(get_speech_synthesis_provider),
    image_understanding: ImageUnderstandingService = Depends(
        get_image_understanding_service
    ),
    conversation: ConversationService = Depends(get_conversation_service),
) -> MultimodalTurnService:
    """Return the provider-neutral spoken-image turn orchestrator."""

    return MultimodalTurnService(
        recognition_provider=recognition,
        synthesis_provider=synthesis,
        image_understanding=image_understanding,
        conversation=conversation,
        metrics=voice_metrics_registry,
    )
