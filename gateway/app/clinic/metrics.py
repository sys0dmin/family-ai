"""Content-free aggregate metrics for pretend-clinic state transitions."""

import threading
from collections import Counter
from datetime import UTC, datetime


class ClinicMetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at = datetime.now(UTC)
        self._counts: Counter[str] = Counter()

    def record(self, operation: str, *, succeeded: bool) -> None:
        outcome = "success" if succeeded else "error"
        with self._lock:
            self._counts[f"{operation}.{outcome}"] += 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "started_at": self._started_at.isoformat(),
                "counts": dict(sorted(self._counts.items())),
            }

    def reset(self) -> None:
        with self._lock:
            self._started_at = datetime.now(UTC)
            self._counts.clear()


clinic_metrics_registry = ClinicMetricsRegistry()
