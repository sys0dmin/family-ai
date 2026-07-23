"""CPU model adapters isolated from the HTTP layer."""

import io
import wave
from collections.abc import Iterable
from typing import Any, Protocol

from family_ai_speech.config import SpeechSettings

SILERO_VOICES = frozenset({"aidar", "baya", "kseniya", "eugene", "xenia"})
VOICE_ALIASES = {
    "lulwa": "xenia",
    "noura": "baya",
    "aisha": "kseniya",
    "fahad": "aidar",
    "alloy": "xenia",
}


def resolve_voice(voice: str | None, default_voice: str) -> str:
    """Map cloud-provider voice names to stable local voices."""

    candidate = (voice or "").strip().lower()
    resolved = VOICE_ALIASES.get(candidate, candidate)
    return resolved if resolved in SILERO_VOICES else default_voice


def pcm16_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap mono signed 16-bit PCM in a finalized WAV container."""

    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return output.getvalue()


class SpeechToTextBackend(Protocol):
    """Minimal speech recognition contract used by orchestration."""

    def transcribe(self, audio: bytes, language: str) -> str: ...


class TextToSpeechBackend(Protocol):
    """Minimal speech synthesis contract used by orchestration."""

    def synthesize(self, text: str, voice: str | None) -> bytes: ...


class FasterWhisperBackend:
    """Transcribe audio with a persistent CTranslate2 Whisper model."""

    def __init__(self, settings: SpeechSettings) -> None:
        from faster_whisper import WhisperModel

        settings.model_cache_dir.mkdir(parents=True, exist_ok=True)
        self._model = WhisperModel(
            settings.stt_model,
            device="cpu",
            compute_type=settings.stt_compute_type,
            cpu_threads=settings.stt_cpu_threads,
            download_root=str(settings.model_cache_dir),
        )
        self._beam_size = settings.stt_beam_size
        self._vad_filter = settings.stt_vad_filter

    def transcribe(self, audio: bytes, language: str) -> str:
        segments, _info = self._model.transcribe(
            io.BytesIO(audio),
            language=language,
            beam_size=self._beam_size,
            vad_filter=self._vad_filter,
            condition_on_previous_text=False,
        )
        return _join_segments(segments)


def _join_segments(segments: Iterable[Any]) -> str:
    return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()


class SileroBackend:
    """Synthesize Russian speech with a persistent Silero model."""

    def __init__(self, settings: SpeechSettings) -> None:
        import torch
        from silero import silero_tts

        torch.set_num_threads(settings.stt_cpu_threads)
        model, _example_text = silero_tts(language="ru", speaker="v5_2_ru")
        self._model = model
        self._torch = torch
        self._default_voice = resolve_voice(
            settings.tts_default_voice,
            default_voice="xenia",
        )
        self._sample_rate = settings.tts_sample_rate

    def synthesize(self, text: str, voice: str | None) -> bytes:
        audio = self._model.apply_tts(
            text=text,
            speaker=resolve_voice(voice, self._default_voice),
            sample_rate=self._sample_rate,
        )
        pcm = (
            (audio.clamp(-1, 1) * 32767)
            .to(self._torch.int16)
            .cpu()
            .numpy()
            .tobytes()
        )
        return pcm16_to_wav(pcm, self._sample_rate)


def build_backends(
    settings: SpeechSettings,
) -> tuple[SpeechToTextBackend, TextToSpeechBackend]:
    """Load both persistent model adapters during application startup."""

    return FasterWhisperBackend(settings), SileroBackend(settings)
