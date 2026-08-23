"""Validated request and response contracts for Gateway runtime settings."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class SettingsResponse(BaseModel):
    environment: str
    message_retention_days: int
    openai_model: str
    openai_base_url: str | None
    speech_base_url: str | None
    stt_base_url: str | None
    stt_model: str
    stt_initial_prompt: str
    tts_base_url: str | None
    tts_model: str
    tts_voice: str
    tts_response_format: Literal["mp3", "wav"]
    web_search_tool_type: Literal["disabled", "browser_search"]
    image_search_provider: Literal["disabled", "openverse"]
    image_search_timeout_seconds: float
    vision_provider: Literal["disabled", "openai_compatible"]
    vision_base_url: str | None
    vision_model: str
    vision_max_image_bytes: int
    has_vision_api_key: bool
    vision_api_key_preview: str
    has_openai_api_key: bool
    openai_api_key_preview: str
    has_speech_api_key: bool
    speech_api_key_preview: str
    has_stt_api_key: bool
    stt_api_key_preview: str
    has_tts_api_key: bool
    tts_api_key_preview: str
    music_recognition_provider: Literal["disabled", "acrcloud"]
    acrcloud_host: str | None
    has_acrcloud_access_key: bool
    acrcloud_access_key_preview: str
    has_acrcloud_access_secret: bool
    acrcloud_access_secret_preview: str
    music_recognition_timeout_seconds: float
    voice_max_in_flight: int
    voice_stt_timeout_seconds: float
    voice_llm_timeout_seconds: float
    voice_tts_timeout_seconds: float
    must_change_password: bool


class SettingsUpdateRequest(BaseModel):
    message_retention_days: int = Field(ge=1, le=3650)
    openai_model: str = Field(min_length=1, max_length=200)
    openai_base_url: str | None = Field(default=None, max_length=500)
    speech_base_url: str | None = Field(default=None, max_length=500)
    stt_base_url: str | None = Field(default=None, max_length=500)
    stt_model: str = Field(min_length=1, max_length=200)
    stt_initial_prompt: str = Field(min_length=1, max_length=1000)
    tts_base_url: str | None = Field(default=None, max_length=500)
    tts_model: str = Field(min_length=1, max_length=200)
    tts_voice: str = Field(min_length=1, max_length=200)
    tts_response_format: Literal["mp3", "wav"]
    web_search_tool_type: Literal["disabled", "browser_search"] = "disabled"
    image_search_provider: Literal["disabled", "openverse"] = "disabled"
    image_search_timeout_seconds: float = Field(default=6.0, ge=1, le=30)
    vision_provider: Literal["disabled", "openai_compatible"] = "disabled"
    vision_base_url: str | None = Field(default=None, max_length=500)
    vision_model: str = Field(min_length=1, max_length=200)
    vision_max_image_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1024 * 1024,
        le=14 * 1024 * 1024,
    )
    vision_api_key: str | None = Field(default=None, max_length=500)
    clear_vision_api_key: bool = False
    openai_api_key: str | None = Field(default=None, max_length=500)
    speech_api_key: str | None = Field(default=None, max_length=500)
    stt_api_key: str | None = Field(default=None, max_length=500)
    tts_api_key: str | None = Field(default=None, max_length=500)
    clear_stt_api_key: bool = False
    clear_tts_api_key: bool = False
    music_recognition_provider: Literal["disabled", "acrcloud"] = "disabled"
    acrcloud_host: str | None = Field(default=None, max_length=500)
    acrcloud_access_key: str | None = Field(default=None, max_length=500)
    acrcloud_access_secret: str | None = Field(default=None, max_length=500)
    music_recognition_timeout_seconds: float = Field(default=8.0, ge=1, le=30)
    voice_max_in_flight: int = Field(default=2, ge=1, le=8)
    voice_stt_timeout_seconds: float = Field(default=60.0, ge=5, le=120)
    voice_llm_timeout_seconds: float = Field(default=20.0, ge=5, le=120)
    voice_tts_timeout_seconds: float = Field(default=30.0, ge=5, le=120)

    @field_validator("*", mode="before")
    @classmethod
    def reject_multiline_environment_values(cls, value: Any) -> Any:
        if isinstance(value, str) and any(character in value for character in "\r\n\0"):
            raise ValueError("configuration values must be single-line")
        return value
