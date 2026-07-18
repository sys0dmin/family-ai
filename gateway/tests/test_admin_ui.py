"""Smoke tests for the standalone parent control room."""

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.admin.main import app as admin_app


@pytest.mark.anyio
async def test_admin_page_exposes_responsive_control_room() -> None:
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://admin") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "Умный дом." in response.text
    assert 'class="admin-shell"' in response.text
    assert 'id="settings-card"' in response.text
    assert 'id="agents-card"' in response.text
    assert 'id="infrastructure-card"' in response.text
    assert 'id="infrastructure-tab"' in response.text
    assert 'id="history-card"' in response.text
    assert "@media (max-width: 820px)" in response.text
    assert "https://cdn" not in response.text
