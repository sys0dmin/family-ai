"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings that are safe to expose within the application."""

    app_name: str = "Family AI Gateway"
    environment: str = "development"
    database_url: str = "sqlite:///./family_ai.db"
    message_retention_days: int = 10
    default_agent_id: str = "teacher_friend"

    # LLM/STT/TTS provider settings
    openai_api_key: SecretStr = SecretStr("sk-placeholder")
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None
    speech_api_key: SecretStr = SecretStr("")
    speech_base_url: str | None = None
    stt_model: str = "gpt-4o-transcribe"
    stt_temperature: float = 0.0
    stt_initial_prompt: str = (
        "Лера, Family AI, Учитель-друг, Почемучка, Сказочник, "
        "Подумай сама, Нотка, Мурка, Байтик."
    )
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"
    tts_response_format: Literal["mp3", "wav"] = "mp3"
    web_search_tool_type: Literal["disabled", "browser_search"] = "disabled"
    image_search_provider: Literal["disabled", "openverse"] = "disabled"
    image_search_timeout_seconds: float = 6.0
    voice_language: str = "ru"
    voice_max_audio_bytes: int = 10 * 1024 * 1024
    calibration_request_timeout_seconds: float = 30.0
    calibration_voice: str = "xenia"

    # Optional music recognition tool for capable agents
    music_recognition_provider: Literal["disabled", "acrcloud"] = "disabled"
    acrcloud_host: str | None = None
    acrcloud_access_key: SecretStr = SecretStr("")
    acrcloud_access_secret: SecretStr = SecretStr("")
    music_recognition_timeout_seconds: float = 8.0

    # Admin panel settings
    admin_username: str = "admin"
    admin_password: SecretStr = SecretStr("change-me")
    admin_force_password_change: bool = True
    admin_env_file: str = ".env"
    admin_session_ttl_hours: int = 12

    # Project infrastructure monitoring (node_exporter endpoints)
    gateway_node_metrics_url: str | None = None
    database_node_metrics_url: str | None = None
    speech_node_metrics_url: str | None = None
    monitoring_request_timeout_seconds: float = 2.0
    gateway_voice_metrics_url: str | None = "http://127.0.0.1:8000/internal/voice-metrics"

    model_config = SettingsConfigDict(
        env_prefix="FAMILY_AI_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the singleton settings instance for the current process."""

    return Settings()
