"""Contract tests for clean-room disaster recovery assets."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_recovery_orchestrator_has_both_guarded_scenarios() -> None:
    script = read("scripts/dr/Invoke-FamilyAiRecovery.ps1")
    common = read("scripts/dr/FamilyAiDr.Common.psm1")

    assert '"TotalLoss", "DatabaseSalvage"' in script
    assert "FamilyAiDr.Common.psm1" in script
    assert "ConfirmTargetsAreDisposable" in script
    assert "Assert-DisposableTargets" in script
    assert "SourceDatabaseHost and target DatabaseHost must be different" in script
    assert "Get-FileHash -Algorithm SHA256" in script
    assert "Compare-Object $sourceManifest $targetManifest" in script
    assert "Target PostgreSQL major version is older than the source" in script
    assert "Remove-Item -LiteralPath $resolvedWork -Recurse -Force" in script
    assert "DatabaseName" in common
    assert "TargetDatabaseHost" in common


def test_database_restore_refuses_nonempty_target_and_is_transactional() -> None:
    script = read("scripts/dr/remote/restore_database_snapshot.sh")

    assert '[[ "$TABLE_COUNT" == "0" ]]' in script
    assert "--single-transaction" in script
    assert "--exit-on-error" in script
    assert "database dump checksum mismatch" in script
    assert 'install -o postgres -g postgres -m 0600 "$DUMP" "$RESTORE_INPUT"' in script


def test_database_snapshot_detects_concurrent_writes() -> None:
    script = read("scripts/dr/remote/create_database_snapshot.sh")

    assert "--serializable-deferrable" in script
    assert 'cmp -s "$BEFORE" "$MANIFEST"' in script
    assert "source database changed during snapshot" in script


def test_logical_restore_validation_never_targets_source_database() -> None:
    script = read("scripts/dr/remote/validate_logical_restore.sh")

    assert '[[ "$SOURCE_DATABASE" != "$TEST_DATABASE" ]]' in script
    assert 'dropdb --if-exists "$TEST_DATABASE"' in script
    assert '"$SCRIPT_DIR/restore_database_snapshot.sh"' in script
    assert 'diff -u "${DUMP}.manifest" "$TARGET_MANIFEST"' in script


def test_dr_secrets_and_dumps_are_excluded_from_git() -> None:
    gitignore = read(".gitignore")

    assert "/.dr/" in gitignore
    assert "*.dump" in gitignore
    assert "*.backup" in gitignore


def test_release_controller_supports_fresh_hosts_with_separate_service_user() -> None:
    release = read("scripts/deploy/release.ps1")
    installer = read("scripts/deploy/install_host.sh")
    remote = read("scripts/deploy/remote_release.sh")

    assert '[string]$ServiceUser = "familyai-deploy"' in release
    assert "'$ServiceUser'" in release
    assert "fresh Gateway host: current will be created during activation" in installer
    assert "fresh Speech host: current will be created during activation" in installer
    assert 'echo "unavailable" >"$COMPONENT_ROOT/deployed-version"' in remote


def test_runbook_documents_two_scenarios_and_fire_drill_boundary() -> None:
    runbook = read("docs/disaster-recovery.md")
    plan = read("plans/DisasterRecoveryPlan.md")

    assert "Сценарий A — потеряно всё" in runbook
    assert "Сценарий B — сервисы потеряны" in runbook
    assert "Invoke-FamilyAiRecovery.ps1 TotalLoss" in runbook
    assert "Invoke-FamilyAiRecovery.ps1 DatabaseSalvage" in runbook
    assert "fire drill" in plan
    assert "- [ ] выполнить первый fire drill" in plan
