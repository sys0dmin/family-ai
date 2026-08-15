"""Tests for reproducible, secret-free release artifacts."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

from scripts.deploy import build_release as BUILDER

REPOSITORY = Path(__file__).resolve().parents[2]


def test_gateway_archive_is_deterministic_and_contains_no_env(tmp_path: Path) -> None:
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"

    first_manifest = BUILDER.build_release(REPOSITORY, "gateway", "HEAD", first)
    second_manifest = BUILDER.build_release(REPOSITORY, "gateway", "HEAD", second)

    assert first.read_bytes() == second.read_bytes()
    assert first_manifest["archive_sha256"] == second_manifest["archive_sha256"]

    with tarfile.open(first, "r:gz") as archive:
        names = set(archive.getnames())
        manifest = json.load(archive.extractfile("release.json"))

    assert "gateway/app/main.py" in names
    assert "alembic.ini" in names
    assert ".env" not in names
    assert not any(name.startswith(".git") for name in names)
    assert manifest["component"] == "gateway"
    assert manifest["commit"] == BUILDER.resolve_commit(REPOSITORY, "HEAD")


def test_speech_archive_has_component_as_its_root(tmp_path: Path) -> None:
    output = tmp_path / "speech.tar.gz"

    BUILDER.build_release(REPOSITORY, "speech", "HEAD", output)

    with tarfile.open(output, "r:gz") as archive:
        names = set(archive.getnames())

    assert "family_ai_speech/main.py" in names
    assert "pyproject.toml" in names
    assert "uv.lock" in names
    assert not any(name.startswith("speech/") for name in names)


def test_gateway_admin_restart_contract_is_fixed_and_unprivileged() -> None:
    admin_unit = (
        REPOSITORY / "infrastructure/systemd/family-ai-admin.service"
    ).read_text(encoding="utf-8")
    restart_unit = (
        REPOSITORY / "infrastructure/systemd/family-ai-gateway-admin.service"
    ).read_text(encoding="utf-8")
    restart_script = (
        REPOSITORY / "scripts/gateway/apply-admin-restart.sh"
    ).read_text(encoding="utf-8")

    assert "NoNewPrivileges=true" in admin_unit
    assert "NoNewPrivileges=true" in restart_unit
    assert "/usr/bin/systemctl restart family-ai-gateway.service" in restart_script
    assert "$1" not in restart_script
