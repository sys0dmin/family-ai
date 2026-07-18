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
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"
    tts_response_format: Literal["mp3", "wav"] = "mp3"
    voice_language: str = "ru"
    voice_max_audio_bytes: int = 10 * 1024 * 1024

    # Admin panel settings
    admin_username: str = "admin"
    admin_password: SecretStr = SecretStr("change-me")
    admin_force_password_change: bool = True
    admin_env_file: str = ".env"

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
