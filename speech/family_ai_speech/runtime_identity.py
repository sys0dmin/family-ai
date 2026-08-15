"""Release identity adapter for the independently deployable Speech Service."""

import json
import re
from pathlib import Path

from family_ai_speech.schemas import RuntimeIdentityResponse

APP_VERSION = "0.1.0"
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


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
    if not isinstance(value, str):
        return None
    normalized = value.lower()
    return normalized if _COMMIT_PATTERN.fullmatch(normalized) else None


def runtime_identity(
    *,
    release_manifest: Path | None = None,
    expected_version_file: Path | None = None,
) -> RuntimeIdentityResponse:
    manifest_path = release_manifest or Path.cwd() / "release.json"
    expected_path = expected_version_file or Path("/srv/family-ai/speech/deployed-version")
    actual_commit = _manifest_commit(manifest_path)
    expected_commit = _read_commit(expected_path)
    return RuntimeIdentityResponse(
        component="speech",
        app_version=APP_VERSION,
        actual_commit=actual_commit,
        expected_commit=expected_commit,
        matches_expected=(
            actual_commit == expected_commit
            if actual_commit is not None and expected_commit is not None
            else None
        ),
    )
