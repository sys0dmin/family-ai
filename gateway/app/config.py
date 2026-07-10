"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings that are safe to expose within the application."""

    app_name: str = "Family AI Gateway"
    environment: str = "development"

    model_config = SettingsConfigDict(
        env_prefix="FAMILY_AI_",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the singleton settings instance for the current process."""

    return Settings()

