"""CPU model adapters isolated from the HTTP layer."""

import io
import math
import wave
from collections.abc import Iterable
from dataclasses import dataclass
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


@dataclass(frozen=True)
class TranscriptionSegment:
    """Provider-neutral timing and confidence data for one STT segment."""

    id: int
    start: float
    end: float
    text: str
    avg_logprob: float
    no_speech_probability: float


@dataclass(frozen=True)
class TranscriptionResult:
    """Text plus privacy-safe diagnostics produced by local STT."""

    text: str
    language: str
    duration_seconds: float
    speech_duration_seconds: float
    confidence: float | None
    no_speech_probability: float | None
    segments: tuple[TranscriptionSegment, ...]


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

    def transcribe(
        self,
        audio: bytes,
        language: str,
        prompt: str | None = None,
    ) -> TranscriptionResult: ...

    def transcribe_with_options(
        self,
        audio: bytes,
        language: str,
        prompt: str | None,
        *,
        beam_size: int,
        vad_filter: bool,
    ) -> TranscriptionResult: ...


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
        self._initial_prompt = settings.stt_initial_prompt
        self._min_speech_seconds = settings.stt_min_speech_seconds
        self._min_confidence = settings.stt_min_confidence
        self._max_no_speech_probability = settings.stt_max_no_speech_probability

    def transcribe(
        self,
        audio: bytes,
        language: str,
        prompt: str | None = None,
    ) -> TranscriptionResult:
        return self.transcribe_with_options(
            audio,
            language,
            prompt,
            beam_size=self._beam_size,
            vad_filter=self._vad_filter,
        )

    def transcribe_with_options(
        self,
        audio: bytes,
        language: str,
        prompt: str | None,
        *,
        beam_size: int,
        vad_filter: bool,
    ) -> TranscriptionResult:
        """Run the loaded model with explicit benchmark options."""

        raw_segments, info = self._model.transcribe(
            io.BytesIO(audio),
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
            condition_on_previous_text=False,
            initial_prompt=(prompt or self._initial_prompt).strip() or None,
        )
        segments = tuple(
            TranscriptionSegment(
                id=index,
                start=float(segment.start),
                end=float(segment.end),
                text=segment.text.strip(),
                avg_logprob=float(segment.avg_logprob),
                no_speech_probability=float(segment.no_speech_prob),
            )
            for index, segment in enumerate(raw_segments)
            if segment.text.strip()
        )
        confidence = _weighted_confidence(segments)
        no_speech_probability = _weighted_no_speech_probability(segments)
        speech_duration = float(getattr(info, "duration_after_vad", 0.0) or 0.0)
        contains_speech = (
            bool(segments)
            and speech_duration >= self._min_speech_seconds
            and (confidence is None or confidence >= self._min_confidence)
            and (
                no_speech_probability is None
                or no_speech_probability <= self._max_no_speech_probability
            )
        )
        return TranscriptionResult(
            text=_join_segments(segments) if contains_speech else "",
            language=str(getattr(info, "language", language) or language),
            duration_seconds=float(getattr(info, "duration", 0.0) or 0.0),
            speech_duration_seconds=speech_duration,
            confidence=confidence,
            no_speech_probability=no_speech_probability,
            segments=segments,
        )


def _join_segments(segments: Iterable[Any]) -> str:
    return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()


def _segment_weight(segment: TranscriptionSegment) -> float:
    return max(0.01, segment.end - segment.start)


def _weighted_confidence(
    segments: tuple[TranscriptionSegment, ...],
) -> float | None:
    if not segments:
        return None
    total_weight = sum(_segment_weight(segment) for segment in segments)
    average_logprob = sum(
        segment.avg_logprob * _segment_weight(segment) for segment in segments
    ) / total_weight
    return round(min(1.0, max(0.0, math.exp(average_logprob))), 4)


def _weighted_no_speech_probability(
    segments: tuple[TranscriptionSegment, ...],
) -> float | None:
    if not segments:
        return None
    total_weight = sum(_segment_weight(segment) for segment in segments)
    probability = sum(
        segment.no_speech_probability * _segment_weight(segment)
        for segment in segments
    ) / total_weight
    return round(min(1.0, max(0.0, probability)), 4)


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
