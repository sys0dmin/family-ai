"""Tests for refresh-safe protected admin browser sessions."""

import base64

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.admin.main import app as admin_app
from gateway.app.config import Settings


@pytest.mark.anyio
async def test_admin_session_survives_requests_without_basic_header(monkeypatch) -> None:
    settings = Settings(
        admin_username="admin",
        admin_password="test-password",
        admin_force_password_change=False,
    )
    monkeypatch.setattr("gateway.admin.auth.get_settings", lambda: settings)
    monkeypatch.setattr("gateway.admin.main.get_settings", lambda: settings)
    credentials = base64.b64encode(b"admin:test-password").decode("ascii")

    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://admin") as client:
        login = await client.post(
            "/api/session",
            headers={"Authorization": f"Basic {credentials}"},
        )
        settings_response = await client.get("/api/settings")
        logout = await client.delete("/api/session")
        after_logout = await client.get("/api/settings")

    assert login.status_code == 204
    assert "httponly" in login.headers["set-cookie"].lower()
    assert "samesite=strict" in login.headers["set-cookie"].lower()
    assert settings_response.status_code == 200
    assert logout.status_code == 204
    assert after_logout.status_code == 401
