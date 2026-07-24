"""Smoke tests for the standalone parent control room."""

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.admin.main import _verify_admin
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
    assert 'id="studio-card"' in response.text
    assert 'id="studio-run"' in response.text
    assert 'id="calibration-start"' in response.text
    assert 'id="calibration-results"' in response.text
    assert 'id="speech-runtime-beam"' in response.text
    assert 'id="speech-runtime-vad"' in response.text
    assert 'id="speech-runtime-apply"' in response.text
    assert 'id="safety-policy-card"' in response.text
    assert 'id="safety-run-scenarios"' in response.text
    assert 'id="safety-reset-metrics"' in response.text
    assert 'id="infrastructure-card"' in response.text
    assert 'id="infrastructure-tab"' in response.text
    assert 'id="server-speech"' in response.text
    assert 'id="pipeline-stt"' in response.text
    assert 'id="history-card"' in response.text
    assert 'href="/admin-assets/admin.css"' in response.text
    assert 'type="module" src="/admin-assets/js/app.js"' in response.text
    assert 'id="image_search_provider"' in response.text
    assert 'id="agent-tool-image-search"' in response.text
    assert 'id="safety-baseline-save"' in response.text
    assert 'id="gateway-restart"' in response.text
    assert "https://cdn" not in response.text


@pytest.mark.anyio
async def test_admin_assets_are_local_modular_components() -> None:
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://admin") as client:
        css = await client.get("/admin-assets/admin.css")
        app = await client.get("/admin-assets/js/app.js")
        navigation = await client.get("/admin-assets/js/navigation.js")
        safety = await client.get("/admin-assets/js/safety-policy-screen.js")
        history = await client.get("/admin-assets/js/history-screen.js")
        infrastructure = await client.get(
            "/admin-assets/js/infrastructure-screen.js"
        )

    assert css.status_code == 200
    assert "@media (max-width: 820px)" in css.text
    assert ".grid.three { grid-template-columns: repeat(3" in css.text
    assert '.option-row input[type="checkbox"]' in css.text
    assert app.status_code == 200
    assert 'from "./api-client.js"' in app.text
    assert "restoreBrowserSession()" in app.text
    assert navigation.status_code == 200
    assert safety.status_code == 200
    assert history.status_code == 200
    assert infrastructure.status_code == 200


@pytest.mark.anyio
async def test_admin_settings_expose_visual_search_configuration() -> None:
    admin_app.dependency_overrides[_verify_admin] = lambda: "admin"
    try:
        transport = ASGITransport(app=admin_app)
        async with AsyncClient(transport=transport, base_url="http://admin") as client:
            response = await client.get("/api/settings")

        assert response.status_code == 200
        body = response.json()
        assert body["image_search_provider"] in {"disabled", "openverse"}
        assert 1 <= body["image_search_timeout_seconds"] <= 30
    finally:
        admin_app.dependency_overrides.clear()
