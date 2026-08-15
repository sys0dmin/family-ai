"""Privacy-safe runtime and client build identity."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import SecretStr

from gateway.app.config import Settings

APP_VERSION = "0.1.0"
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:\+\d+)?$")
_PROCESS_STARTED = time.perf_counter()
_FINGERPRINT_EXCLUDED = {
    "database_url",
    "admin_username",
    "admin_env_file",
    "admin_config_history_dir",
}


def configuration_fingerprint(settings: Settings) -> str:
    """Hash canonical effective settings without secrets or database credentials."""

    safe: dict[str, object] = {}
    for name in type(settings).model_fields:
        value = getattr(settings, name)
        if name in _FINGERPRINT_EXCLUDED or isinstance(value, SecretStr):
            continue
        if isinstance(value, Path):
            value = str(value)
        safe[name] = value
    payload = json.dumps(
        safe,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read_commit(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return None
    return value if _COMMIT_PATTERN.fullmatch(value) else None


def _manifest_commit(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    value = payload.get("commit") if isinstance(payload, dict) else None
    return (
        value.lower()
        if isinstance(value, str) and _COMMIT_PATTERN.fullmatch(value.lower())
        else None
    )


@dataclass(frozen=True)
class ObservedClientBuild:
    version: str
    source_commit: str
    observed_at: datetime

    def as_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "source_commit": self.source_commit,
            "observed_at": self.observed_at.isoformat(),
        }


class ClientBuildRegistry:
    """Keep only the latest anonymous Android build observation in memory."""

    def __init__(self) -> None:
        self._latest: ObservedClientBuild | None = None
        self._lock = threading.Lock()

    def observe(self, version: str | None, source_commit: str | None) -> None:
        normalized_version = (version or "").strip()
        normalized_commit = (source_commit or "").strip().lower()
        if not _VERSION_PATTERN.fullmatch(normalized_version):
            return
        if not _COMMIT_PATTERN.fullmatch(normalized_commit):
            return
        with self._lock:
            self._latest = ObservedClientBuild(
                version=normalized_version,
                source_commit=normalized_commit,
                observed_at=datetime.now(UTC),
            )

    def snapshot(self) -> dict[str, object] | None:
        with self._lock:
            return self._latest.as_dict() if self._latest else None

    def reset(self) -> None:
        with self._lock:
            self._latest = None


client_build_registry = ClientBuildRegistry()


def runtime_identity(
    settings: Settings,
    *,
    release_manifest: Path | None = None,
    expected_version_file: Path | None = None,
) -> dict[str, object]:
    """Describe the running Gateway without exposing environment values."""

    manifest_path = release_manifest or Path.cwd() / "release.json"
    expected_path = expected_version_file or Path("/srv/family-ai/gateway/deployed-version")
    actual_commit = _manifest_commit(manifest_path)
    expected_commit = _read_commit(expected_path)
    return {
        "component": "gateway",
        "app_version": APP_VERSION,
        "actual_commit": actual_commit,
        "expected_commit": expected_commit,
        "matches_expected": (
            actual_commit == expected_commit
            if actual_commit is not None and expected_commit is not None
            else None
        ),
        "uptime_seconds": round(time.perf_counter() - _PROCESS_STARTED, 1),
        "config_fingerprint": configuration_fingerprint(settings),
        "android": client_build_registry.snapshot(),
    }
