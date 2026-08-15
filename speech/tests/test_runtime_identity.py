"""Speech release identity tests."""

import json
from pathlib import Path

from family_ai_speech.runtime_identity import runtime_identity


def test_speech_runtime_identity_detects_deployment_drift(tmp_path: Path) -> None:
    manifest = tmp_path / "release.json"
    expected = tmp_path / "deployed-version"
    manifest.write_text(json.dumps({"commit": "a" * 40}), encoding="utf-8")
    expected.write_text("b" * 40, encoding="utf-8")

    identity = runtime_identity(
        release_manifest=manifest,
        expected_version_file=expected,
    )

    assert identity.actual_commit == "a" * 40
    assert identity.expected_commit == "b" * 40
    assert identity.matches_expected is False
