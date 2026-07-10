"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings that are safe to expose within the application."""

    app_name: str = "Family AI Gateway"
    environment: str = "development"
    database_url: str = "sqlite:///./family_ai.db"
    message_retention_days: int = 10

    # OpenAI Settings
    openai_api_key: SecretStr = SecretStr("sk-placeholder")
    openai_model: str = "gpt-4o-mini"

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

