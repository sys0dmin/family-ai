"""Runtime identity must detect drift without exposing secret values."""

import json
from pathlib import Path

import pytest
from httpx import AsyncClient

from gateway.app.config import Settings
from gateway.app.observability.runtime_identity import (
    ClientBuildRegistry,
    client_build_registry,
    configuration_fingerprint,
    runtime_identity,
)


def test_runtime_identity_compares_manifest_with_deployment_marker(tmp_path: Path) -> None:
    commit = "a" * 40
    manifest = tmp_path / "release.json"
    expected = tmp_path / "deployed-version"
    manifest.write_text(json.dumps({"commit": commit}), encoding="utf-8")
    expected.write_text(commit, encoding="utf-8")

    identity = runtime_identity(
        Settings(environment="test"),
        release_manifest=manifest,
        expected_version_file=expected,
    )

    assert identity["actual_commit"] == commit
    assert identity["expected_commit"] == commit
    assert identity["matches_expected"] is True
    assert len(identity["config_fingerprint"]) == 64


def test_configuration_fingerprint_excludes_secrets_but_tracks_safe_settings() -> None:
    first = Settings(openai_api_key="secret-one", openai_model="model-a")
    secret_changed = Settings(openai_api_key="secret-two", openai_model="model-a")
    model_changed = Settings(openai_api_key="secret-one", openai_model="model-b")

    assert configuration_fingerprint(first) == configuration_fingerprint(secret_changed)
    assert configuration_fingerprint(first) != configuration_fingerprint(model_changed)


def test_client_build_registry_keeps_only_valid_anonymous_build() -> None:
    registry = ClientBuildRegistry()
    registry.observe("development", "not-a-commit")
    assert registry.snapshot() is None

    registry.observe("1.6.0+8", "b" * 40)

    snapshot = registry.snapshot()
    assert snapshot is not None
    assert snapshot["version"] == "1.6.0+8"
    assert snapshot["source_commit"] == "b" * 40


@pytest.mark.anyio
async def test_gateway_observes_build_headers_without_device_identity(
    client: AsyncClient,
) -> None:
    client_build_registry.reset()
    commit = "d" * 40

    await client.get(
        "/healthz",
        headers={
            "X-Family-AI-App-Version": "1.6.0+8",
            "X-Family-AI-App-Commit": commit,
        },
    )
    response = await client.get("/internal/runtime-identity")

    android = response.json()["android"]
    assert android["version"] == "1.6.0+8"
    assert android["source_commit"] == commit
    assert set(android) == {"version", "source_commit", "observed_at"}
    client_build_registry.reset()
