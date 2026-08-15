"""Tests for narrowly scoped operational actions in the admin panel."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.admin.auth import verify_admin
from gateway.admin.main import app as admin_app
from gateway.admin.system_router import get_gateway_system_service
from gateway.admin.system_service import (
    GatewayRestartError,
    GatewayRestartResult,
    GatewaySystemService,
)


class SuccessfulSystemService:
    def restart_gateway(self) -> GatewayRestartResult:
        return GatewayRestartResult(
            service="family-ai-gateway.service",
            active=True,
        )


class FailedSystemService:
    def restart_gateway(self) -> GatewayRestartResult:
        raise GatewayRestartError("rejected")


def test_system_service_uses_nonce_request_without_privileged_command(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    request_path = tmp_path / "restart.request"
    ack_path = tmp_path / "restart.ack"
    nonce = "a" * 32
    ack_path.write_text(nonce + "\n", encoding="ascii")

    def fake_run(
        command: tuple[str, ...],
        *,
        check: bool,
        capture_output: bool,
        timeout: int,
    ) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(
        "gateway.admin.system_service.subprocess.run",
        fake_run,
    )
    monkeypatch.setattr(
        "gateway.admin.system_service.secrets.token_hex",
        lambda _size: nonce,
    )

    result = GatewaySystemService(
        request_path=request_path,
        ack_path=ack_path,
    ).restart_gateway()

    assert result.active
    assert request_path.read_text(encoding="ascii") == nonce + "\n"
    assert calls == [
        (
            "/usr/bin/systemctl",
            "is-active",
            "--quiet",
            "family-ai-gateway.service",
        ),
    ]


def test_system_service_rejects_missing_acknowledgement(tmp_path: Path) -> None:
    service = GatewaySystemService(
        request_path=tmp_path / "restart.request",
        ack_path=tmp_path / "restart.ack",
    )

    with pytest.raises(
        GatewayRestartError,
        match="acknowledgement timed out",
    ):
        service._wait_for_ack("a" * 32, timeout_seconds=0)


def test_verified_restart_waits_for_loopback_gateway_health(monkeypatch) -> None:
    service = GatewaySystemService()
    monkeypatch.setattr(
        service,
        "restart_gateway",
        lambda: GatewayRestartResult(
            service="family-ai-gateway.service",
            active=True,
        ),
    )

    class HealthyResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr(
        "gateway.admin.system_service.urlopen",
        lambda *_args, **_kwargs: HealthyResponse(),
    )

    result = service.restart_gateway_verified(timeout_seconds=1)

    assert result.active is True


@pytest.mark.anyio
async def test_gateway_restart_requires_admin_authentication() -> None:
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://admin") as client:
        response = await client.post("/api/system/gateway/restart")

    assert response.status_code == 401


@pytest.mark.anyio
async def test_admin_can_restart_only_the_gateway_service() -> None:
    admin_app.dependency_overrides[verify_admin] = lambda: "admin"
    admin_app.dependency_overrides[get_gateway_system_service] = SuccessfulSystemService
    try:
        transport = ASGITransport(app=admin_app)
        async with AsyncClient(transport=transport, base_url="http://admin") as client:
            response = await client.post("/api/system/gateway/restart")
    finally:
        admin_app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "restarted",
        "service": "family-ai-gateway.service",
        "active": True,
    }


@pytest.mark.anyio
async def test_gateway_restart_failure_is_reported_without_command_details() -> None:
    admin_app.dependency_overrides[verify_admin] = lambda: "admin"
    admin_app.dependency_overrides[get_gateway_system_service] = FailedSystemService
    try:
        transport = ASGITransport(app=admin_app)
        async with AsyncClient(transport=transport, base_url="http://admin") as client:
            response = await client.post("/api/system/gateway/restart")
    finally:
        admin_app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Gateway service could not be restarted",
    }
