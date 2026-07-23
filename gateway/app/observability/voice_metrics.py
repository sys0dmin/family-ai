"""Privacy-preserving metrics for the voice conversation pipeline."""

from collections import Counter, deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from statistics import fmean
from threading import Lock


@dataclass(frozen=True)
class VoiceTurnSample:
    """One anonymized voice turn timing sample."""

    timestamp: str
    status: str
    recording_duration_ms: int | None
    stt_duration_ms: int | None
    llm_duration_ms: int | None
    tts_duration_ms: int | None
    total_duration_ms: int
    stt_confidence: float | None = None
    error_stage: str | None = None


class VoiceMetricsRegistry:
    """Keep a small bounded metrics window without conversation data."""

    def __init__(self, max_samples: int = 100) -> None:
        self._samples: deque[VoiceTurnSample] = deque(maxlen=max_samples)
        self._lock = Lock()

    def record(
        self,
        *,
        status: str,
        total_duration_ms: int,
        recording_duration_ms: int | None = None,
        stt_duration_ms: int | None = None,
        llm_duration_ms: int | None = None,
        tts_duration_ms: int | None = None,
        stt_confidence: float | None = None,
        error_stage: str | None = None,
    ) -> None:
        sample = VoiceTurnSample(
            timestamp=datetime.now(UTC).isoformat(),
            status=status,
            recording_duration_ms=recording_duration_ms,
            stt_duration_ms=stt_duration_ms,
            llm_duration_ms=llm_duration_ms,
            tts_duration_ms=tts_duration_ms,
            total_duration_ms=total_duration_ms,
            stt_confidence=stt_confidence,
            error_stage=error_stage,
        )
        with self._lock:
            self._samples.append(sample)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            samples = list(self._samples)

        return {
            "window_size": len(samples),
            "successes": sum(sample.status == "success" for sample in samples),
            "errors": sum(sample.status != "success" for sample in samples),
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
                    "tts_duration_ms",
                    "total_duration_ms",
                )
            },
            "recent": [asdict(sample) for sample in samples[-20:]],
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
