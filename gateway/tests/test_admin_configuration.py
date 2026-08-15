"""Tests for bounded, secret-safe Gateway configuration revisions."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.admin.auth import verify_admin
from gateway.admin.configuration_schemas import (
    ConfigurationChange,
    ConfigurationRevisionResponse,
)
from gateway.admin.configuration_service import (
    ConfigurationApplyError,
    ConfigurationValidationError,
    GatewayConfigurationService,
    parse_env_text,
)
from gateway.admin.main import (
    app as admin_app,
)
from gateway.admin.main import (
    get_gateway_configuration_service,
)
from gateway.admin.system_service import GatewayRestartError, GatewayRestartResult
from gateway.app.config import Settings, get_settings


class StubSystemService:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls = 0

    def restart_gateway_verified(self) -> GatewayRestartResult:
        self.calls += 1
        if self.calls <= self.failures:
            raise GatewayRestartError("not ready")
        return GatewayRestartResult(service="family-ai-gateway.service", active=True)


class StubConfigurationService:
    def __init__(self) -> None:
        self.applied = False
        self.revision = ConfigurationRevisionResponse(
            id="20260815T120000-abcdef",
            created_at=datetime.now(UTC),
            actor="admin",
            operation="apply",
            status="active",
            fingerprint="123456789abc",
            changes=[
                ConfigurationChange(
                    key="openai_model",
                    before="model-a",
                    after="model-b",
                )
            ],
        )

    def preview(self, _updates) -> list[ConfigurationChange]:
        return self.revision.changes

    def apply(self, _updates, *, actor: str) -> ConfigurationRevisionResponse:
        self.applied = True
        return self.revision.model_copy(update={"actor": actor})

    def list_revisions(self) -> list[ConfigurationRevisionResponse]:
        return [self.revision]

    def rollback(self, _revision_id: str, *, actor: str) -> ConfigurationRevisionResponse:
        return self.revision.model_copy(
            update={"actor": actor, "operation": "rollback"}
        )


def _service(
    tmp_path: Path,
    *,
    system: StubSystemService | None = None,
) -> tuple[GatewayConfigurationService, Path, Path, StubSystemService]:
    env_path = tmp_path / "gateway.env"
    env_path.write_text(
        "\n".join(
            [
                "FAMILY_AI_DATABASE_URL=postgresql://db/family_ai",
                "FAMILY_AI_ADMIN_PASSWORD=keep-me",
                "FAMILY_AI_OPENAI_MODEL=model-a",
                "FAMILY_AI_OPENAI_API_KEY=secret-a",
                "FAMILY_AI_MESSAGE_RETENTION_DAYS=10",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    history = tmp_path / "history"
    restarter = system or StubSystemService()
    settings = Settings(
        database_url="postgresql://db/family_ai",
        admin_password="keep-me",
        openai_model="model-a",
        openai_api_key="secret-a",
        message_retention_days=10,
    )
    return (
        GatewayConfigurationService(
            env_path=env_path,
            history_dir=history,
            settings=settings,
            system_service=restarter,  # type: ignore[arg-type]
        ),
        env_path,
        history,
        restarter,
    )


def test_preview_redacts_secrets_and_does_not_write(tmp_path: Path) -> None:
    service, env_path, history, restarter = _service(tmp_path)
    before = env_path.read_bytes()

    changes = service.preview(
        {
            "FAMILY_AI_OPENAI_MODEL": "model-b",
            "FAMILY_AI_OPENAI_API_KEY": "secret-b",
        }
    )

    assert {item.key for item in changes} == {"openai_model", "openai_api_key"}
    secret = next(item for item in changes if item.secret)
    assert secret.before == "настроен"
    assert secret.after == "настроен"
    assert env_path.read_bytes() == before
    assert not history.exists()
    assert restarter.calls == 0


def test_preview_rejects_environment_line_injection(tmp_path: Path) -> None:
    service, env_path, history, restarter = _service(tmp_path)
    before = env_path.read_bytes()

    with pytest.raises(ConfigurationValidationError, match="single-line"):
        service.preview(
            {
                "FAMILY_AI_OPENAI_MODEL": (
                    "model-b\nFAMILY_AI_DATABASE_URL=postgresql://attacker/db"
                )
            }
        )

    assert env_path.read_bytes() == before
    assert not history.exists()
    assert restarter.calls == 0


def test_apply_is_atomic_versioned_and_preserves_unmanaged_values(tmp_path: Path) -> None:
    service, env_path, history, restarter = _service(tmp_path)

    applied = service.apply(
        {
            "FAMILY_AI_OPENAI_MODEL": "model-b",
            "FAMILY_AI_OPENAI_API_KEY": "secret-b",
        },
        actor="admin",
    )

    assert applied is not None
    assert applied.status == "active"
    assert restarter.calls == 1
    values = parse_env_text(env_path.read_text(encoding="utf-8"))
    assert values["FAMILY_AI_OPENAI_MODEL"] == "model-b"
    assert values["FAMILY_AI_OPENAI_API_KEY"] == "secret-b"
    assert values["FAMILY_AI_DATABASE_URL"] == "postgresql://db/family_ai"
    assert values["FAMILY_AI_ADMIN_PASSWORD"] == "keep-me"

    revisions = service.list_revisions()
    assert [item.status for item in revisions] == ["active", "superseded"]
    metadata = (history / f"{applied.id}.json").read_text(encoding="utf-8")
    assert "secret-b" not in metadata
    assert "secret-b" in (history / f"{applied.id}.env").read_text(encoding="utf-8")


def test_rollback_restores_only_managed_values(tmp_path: Path) -> None:
    service, env_path, _history, restarter = _service(tmp_path)
    service.apply({"FAMILY_AI_OPENAI_MODEL": "model-b"}, actor="admin")
    baseline = next(item for item in service.list_revisions() if item.operation == "baseline")
    env_path.write_text(
        env_path.read_text(encoding="utf-8").replace(
            "FAMILY_AI_ADMIN_PASSWORD=keep-me",
            "FAMILY_AI_ADMIN_PASSWORD=new-admin-password",
        ),
        encoding="utf-8",
    )

    rollback = service.rollback(baseline.id, actor="admin")

    values = parse_env_text(env_path.read_text(encoding="utf-8"))
    assert rollback.operation == "rollback"
    assert rollback.source_revision_id == baseline.id
    assert values["FAMILY_AI_OPENAI_MODEL"] == "model-a"
    assert values["FAMILY_AI_ADMIN_PASSWORD"] == "new-admin-password"
    assert restarter.calls == 2


def test_failed_apply_restores_previous_file_and_records_attempt(tmp_path: Path) -> None:
    system = StubSystemService(failures=1)
    service, env_path, _history, restarter = _service(tmp_path, system=system)
    before = env_path.read_bytes()

    with pytest.raises(ConfigurationApplyError, match="restored"):
        service.apply({"FAMILY_AI_OPENAI_MODEL": "broken"}, actor="admin")

    assert env_path.read_bytes() == before
    assert restarter.calls == 2
    assert any(item.status == "rolled_back" for item in service.list_revisions())
    assert any(item.status == "active" for item in service.list_revisions())


def test_environment_write_failure_is_reported_without_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, env_path, _history, restarter = _service(tmp_path)
    before = env_path.read_bytes()

    def reject_write(_content: str) -> None:
        raise OSError("read-only")

    monkeypatch.setattr(service, "_write_env_atomic", reject_write)

    with pytest.raises(ConfigurationApplyError, match="persisted"):
        service.apply({"FAMILY_AI_OPENAI_MODEL": "model-b"}, actor="admin")

    assert env_path.read_bytes() == before
    assert restarter.calls == 0
    assert any(item.status == "rolled_back" for item in service.list_revisions())


def test_admin_settings_reload_values_from_authoritative_env_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_path = tmp_path / "gateway.env"
    env_path.write_text(
        "FAMILY_AI_OPENAI_MODEL=file-model\n"
        "FAMILY_AI_ADMIN_PASSWORD=file-password\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FAMILY_AI_ADMIN_ENV_FILE", str(env_path))
    monkeypatch.setenv("FAMILY_AI_OPENAI_MODEL", "stale-process-model")
    get_settings.cache_clear()
    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.openai_model == "file-model"
    assert settings.admin_password.get_secret_value() == "file-password"


def _settings_payload() -> dict[str, object]:
    return {
        "message_retention_days": 10,
        "openai_model": "model-b",
        "openai_base_url": None,
        "speech_base_url": None,
        "stt_base_url": None,
        "stt_model": "whisper",
        "stt_initial_prompt": "Лера, Мурка, Байтик",
        "tts_base_url": None,
        "tts_model": "silero",
        "tts_voice": "xenia",
        "tts_response_format": "wav",
        "vision_model": "vision-model",
    }


@pytest.mark.anyio
async def test_configuration_lifecycle_api_is_protected_and_secret_free() -> None:
    service = StubConfigurationService()
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://admin") as client:
        denied = await client.get("/api/settings/revisions")
    assert denied.status_code == 401

    admin_app.dependency_overrides[verify_admin] = lambda: "admin"
    admin_app.dependency_overrides[get_gateway_configuration_service] = lambda: service
    try:
        async with AsyncClient(transport=transport, base_url="http://admin") as client:
            preview = await client.post(
                "/api/settings/preview",
                json=_settings_payload(),
            )
            revisions = await client.get("/api/settings/revisions")
            rollback = await client.post(
                f"/api/settings/revisions/{service.revision.id}/rollback"
            )
    finally:
        admin_app.dependency_overrides.clear()

    assert preview.status_code == 200
    assert preview.json()["changes"][0]["before"] == "model-a"
    assert revisions.json()["items"][0]["fingerprint"] == "123456789abc"
    assert rollback.status_code == 200
    assert rollback.json()["revision"]["operation"] == "rollback"
