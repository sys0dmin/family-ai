"""Privacy-preserving metrics for the voice conversation pipeline."""

from collections import Counter, deque
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from statistics import fmean
from threading import Lock


@dataclass(frozen=True)
class VoiceTurnSample:
    """One anonymized voice turn timing sample."""

    timestamp: str
    mode: str
    status: str
    recording_duration_ms: int | None
    stt_duration_ms: int | None
    llm_duration_ms: int | None
    vision_duration_ms: int | None
    tts_duration_ms: int | None
    total_duration_ms: int
    stt_confidence: float | None = None
    error_stage: str | None = None
    streamed: bool = False
    first_audio_ready_ms: int | None = None
    client_first_playback_ms: int | None = None
    chunk_count: int | None = None
    cancelled: bool = False
    turn_id: str | None = None


class VoiceMetricsRegistry:
    """Keep a small bounded metrics window without conversation data."""

    def __init__(self, max_samples: int = 100) -> None:
        self._samples: deque[VoiceTurnSample] = deque(maxlen=max_samples)
        self._pending_playback: dict[str, int] = {}
        self._lock = Lock()

    def record(
        self,
        *,
        status: str,
        total_duration_ms: int,
        mode: str = "voice",
        recording_duration_ms: int | None = None,
        stt_duration_ms: int | None = None,
        llm_duration_ms: int | None = None,
        vision_duration_ms: int | None = None,
        tts_duration_ms: int | None = None,
        stt_confidence: float | None = None,
        error_stage: str | None = None,
        streamed: bool = False,
        first_audio_ready_ms: int | None = None,
        client_first_playback_ms: int | None = None,
        chunk_count: int | None = None,
        cancelled: bool = False,
        turn_id: str | None = None,
    ) -> None:
        with self._lock:
            reported_playback = (
                self._pending_playback.pop(turn_id, None) if turn_id else None
            )
            sample = VoiceTurnSample(
                timestamp=datetime.now(UTC).isoformat(),
                mode=mode,
                status=status,
                recording_duration_ms=recording_duration_ms,
                stt_duration_ms=stt_duration_ms,
                llm_duration_ms=llm_duration_ms,
                vision_duration_ms=vision_duration_ms,
                tts_duration_ms=tts_duration_ms,
                total_duration_ms=total_duration_ms,
                stt_confidence=stt_confidence,
                error_stage=error_stage,
                streamed=streamed,
                first_audio_ready_ms=first_audio_ready_ms,
                client_first_playback_ms=(
                    client_first_playback_ms
                    if client_first_playback_ms is not None
                    else reported_playback
                ),
                chunk_count=chunk_count,
                cancelled=cancelled,
                turn_id=turn_id,
            )
            self._samples.append(sample)

    def report_client_playback(self, turn_id: str, duration_ms: int) -> None:
        """Attach one privacy-safe client playback timing to its stream sample."""

        with self._lock:
            for index in range(len(self._samples) - 1, -1, -1):
                sample = self._samples[index]
                if sample.turn_id == turn_id:
                    self._samples[index] = replace(
                        sample,
                        client_first_playback_ms=duration_ms,
                    )
                    return
            if len(self._pending_playback) >= 200:
                self._pending_playback.pop(next(iter(self._pending_playback)))
            self._pending_playback[turn_id] = duration_ms

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            samples = list(self._samples)

        return {
            "window_size": len(samples),
            "successes": sum(sample.status == "success" for sample in samples),
            "errors": sum(sample.status == "error" for sample in samples),
            "cancellations": sum(sample.cancelled for sample in samples),
            "error_stages": dict(
                Counter(
                    sample.error_stage
                    for sample in samples
                    if sample.error_stage is not None
                )
            ),
            "stages": {
                field.removesuffix("_duration_ms"): self._stage_summary(samples, field)
                for field in (
                    "recording_duration_ms",
                    "stt_duration_ms",
                    "llm_duration_ms",
                    "vision_duration_ms",
                    "tts_duration_ms",
                    "first_audio_ready_ms",
                    "client_first_playback_ms",
                    "total_duration_ms",
                )
            },
            "recent": [
                {
                    key: value
                    for key, value in asdict(sample).items()
                    if key != "turn_id"
                }
                for sample in samples[-20:]
            ],
        }

    @staticmethod
    def _stage_summary(
        samples: list[VoiceTurnSample],
        field: str,
    ) -> dict[str, int | None]:
        values = [
            value
            for sample in samples
            if (value := getattr(sample, field)) is not None
        ]
        if not values:
            return {"average_ms": None, "p95_ms": None, "last_ms": None}
        ordered = sorted(values)
        p95_index = min(len(ordered) - 1, max(0, round(len(ordered) * 0.95) - 1))
        return {
            "average_ms": round(fmean(values)),
            "p95_ms": ordered[p95_index],
            "last_ms": values[-1],
        }


voice_metrics_registry = VoiceMetricsRegistry()
