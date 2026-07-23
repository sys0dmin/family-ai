"""Optional diagnostics emitted by conversation orchestration."""

from dataclasses import dataclass


@dataclass
class TurnDiagnostics:
    """Non-persistent timing data for one conversation turn."""

    llm_duration_ms: int | None = None
