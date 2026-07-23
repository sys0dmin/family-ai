"""Runtime configuration for the local speech service."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class SpeechSettings(BaseSettings):
    """Configuration loaded independently from the Gateway."""

    api_key: SecretStr = SecretStr("")
    stt_model: str = "base"
    stt_compute_type: str = "int8"
    stt_cpu_threads: int = Field(default=4, ge=1, le=32)
    stt_beam_size: int = Field(default=1, ge=1, le=10)
    stt_vad_filter: bool = True
    model_cache_dir: Path = Path("/var/lib/family-ai-speech/models")
    tts_model: str = "silero-v5_2-ru"
    tts_default_voice: str = "xenia"
    tts_sample_rate: int = Field(default=48000, ge=8000, le=48000)
    max_audio_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    max_text_characters: int = Field(default=4000, ge=1, le=10000)

    model_config = SettingsConfigDict(
        env_prefix="FAMILY_AI_SPEECH_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )
