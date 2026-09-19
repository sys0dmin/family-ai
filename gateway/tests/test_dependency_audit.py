"""Regression coverage for dependency-audit failure handling."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.release import audit_dependencies


def test_audit_retries_transient_advisory_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = 0

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return subprocess.CompletedProcess(
                command,
                1,
                "",
                "requests.exceptions.ReadTimeout: advisory service timed out",
            )
        report = Path(command[-1])
        report.write_text(json.dumps({"dependencies": [{"name": "anyio"}]}), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(audit_dependencies.subprocess, "run", fake_run)
    monkeypatch.setattr(audit_dependencies.time, "sleep", lambda _: None)

    result = audit_dependencies._audit(
        Path("uv"), tmp_path / "requirements.txt", tmp_path / "report.json"
    )

    assert result == {"dependencies": [{"name": "anyio"}]}
    assert calls == 2


def test_audit_does_not_retry_vulnerability_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = 0

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        Path(command[-1]).write_text(
            json.dumps({"dependencies": [{"name": "anyio", "vulns": [{"id": "CVE"}]}]}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 1, "known vulnerability", "")

    monkeypatch.setattr(audit_dependencies.subprocess, "run", fake_run)

    with pytest.raises(subprocess.CalledProcessError):
        audit_dependencies._audit(
            Path("uv"), tmp_path / "requirements.txt", tmp_path / "report.json"
        )

    assert calls == 1
