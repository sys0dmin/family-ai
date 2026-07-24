"""Content-free aggregate policy decision metrics."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock

from gateway.app.safety.contracts import PolicyOutcome


@dataclass(frozen=True)
class PolicyMetric:
    rule_id: str
    count: int


class SafetyMetricsRegistry:
    """Count rule IDs only; never receive or retain child text."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counts: Counter[str] = Counter()
        self._started_at = datetime.now(UTC)

    def record(self, outcome: PolicyOutcome) -> None:
        with self._lock:
            self._counts.update(decision.rule_id for decision in outcome.decisions)

    def snapshot(self) -> tuple[datetime, tuple[PolicyMetric, ...]]:
        with self._lock:
            metrics = tuple(
                PolicyMetric(rule_id=rule_id, count=count)
                for rule_id, count in sorted(
                    self._counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            )
            return self._started_at, metrics

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()
            self._started_at = datetime.now(UTC)


safety_metrics_registry = SafetyMetricsRegistry()
