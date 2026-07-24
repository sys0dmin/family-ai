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
    stt_beam_size: int = Field(default=5, ge=1, le=10)
    stt_vad_filter: bool = True
    stt_initial_prompt: str = (
        "Лера, Family AI, Учитель-друг, Почемучка, Сказочник, "
        "Подумай сама, Нотка, Мурка, Байтик."
    )
    stt_min_speech_seconds: float = Field(default=0.25, ge=0, le=5)
    stt_min_confidence: float = Field(default=0.12, ge=0, le=1)
    stt_max_no_speech_probability: float = Field(default=0.8, ge=0, le=1)
    model_cache_dir: Path = Path("/var/lib/family-ai-speech/models")
    tts_model: str = "silero-v5_2-ru"
    tts_default_voice: str = "xenia"
    tts_sample_rate: int = Field(default=48000, ge=8000, le=48000)
    max_audio_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    max_text_characters: int = Field(default=4000, ge=1, le=10000)
    calibration_dir: Path = Path("/var/lib/family-ai-speech/calibration")
    calibration_expiry_hours: int = Field(default=24, ge=1, le=168)
    runtime_settings_path: Path = Path("/var/lib/family-ai-speech/runtime.env")
    restart_request_path: Path = Path(
        "/var/lib/family-ai-speech/restart.request"
    )

    model_config = SettingsConfigDict(
        env_prefix="FAMILY_AI_SPEECH_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )
