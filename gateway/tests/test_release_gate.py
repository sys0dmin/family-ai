"""Local release gate policy and deployment safety contracts."""

from __future__ import annotations

from pathlib import Path

from scripts.release.repository_policy import inspect_paths

REPOSITORY = Path(__file__).resolve().parents[2]


def test_current_tracked_repository_passes_content_policy() -> None:
    from scripts.release.repository_policy import tracked_paths

    existing_paths = [
        path for path in tracked_paths(REPOSITORY) if (REPOSITORY / path).is_file()
    ]
    assert inspect_paths(REPOSITORY, existing_paths) == []


def test_repository_policy_rejects_secret_artifact_and_large_file(tmp_path: Path) -> None:
    (tmp_path / ".env.production").write_text("SAFE=value", encoding="utf-8")
    (tmp_path / "token.txt").write_text("sk-" + "A" * 32, encoding="utf-8")
    (tmp_path / "application.apk").write_bytes(b"apk")
    (tmp_path / "large.bin").write_bytes(b"x" * 65)

    violations = inspect_paths(
        tmp_path,
        [".env.production", "token.txt", "application.apk", "large.bin"],
        max_bytes=64,
    )
    reasons = {(item.path, item.reason) for item in violations}

    assert (".env.production", "environment file is forbidden") in reasons
    assert ("token.txt", "high-confidence OpenAI-style API key detected") in reasons
    assert ("application.apk", "forbidden artifact type .apk") in reasons
    assert any(path == "large.bin" and "larger than" in reason for path, reason in reasons)


def test_gateway_activation_checks_schema_before_switching_release() -> None:
    remote = (REPOSITORY / "scripts/deploy/remote_release.sh").read_text(encoding="utf-8")

    assert "assert_gateway_schema_ready" in remote
    assert 'activate_release "$COMPONENT" "$5" true true' in remote
    assert 'activate_release "$component" "$(basename "$target")" false false' in remote


def test_release_gate_covers_every_local_release_boundary() -> None:
    gate = (REPOSITORY / "scripts/release/Invoke-LocalReleaseGate.ps1").read_text(encoding="utf-8")

    for stage in (
        "repository_policy",
        "working_tree_clean",
        "gateway_lock",
        "speech_lock",
        "character_assets",
        "dependency_audit",
        "ruff",
        "gateway_tests",
        "speech_tests",
        "flutter_analyze",
        "flutter_tests",
        "admin_visual",
        "markdown_links",
        "alembic_head",
        "postgres_migrations",
        "release_archives",
    ):
        assert f'Invoke-GateStage "{stage}"' in gate
    assert 'Join-Path $RepoRoot ".venv\\Scripts\\uv.exe"' in gate
    assert "& $Uv lock --check" in gate
    assert "status --porcelain" in gate
    assert "Release gate requires a clean working tree" in gate
    assert "--no-pub" in gate
