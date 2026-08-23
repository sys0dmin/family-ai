"""Atomic helpers for the Admin-owned environment file."""

from pathlib import Path

from gateway.admin.configuration_service import render_env_updates


def upsert_env_values(path: Path, updates: dict[str, str]) -> None:
    """Atomically update selected values without exposing their contents."""

    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(render_env_updates(lines, updates), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
