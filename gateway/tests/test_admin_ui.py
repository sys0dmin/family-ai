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
    assert response.headers["cache-control"] == "no-store"
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
    assert 'id="memory-card"' in response.text
    assert 'id="memory-save"' in response.text
    assert 'id="infrastructure-card"' in response.text
    assert 'id="infrastructure-tab"' in response.text
    assert 'id="server-speech"' in response.text
    assert 'id="pipeline-stt"' in response.text
    assert 'id="operational-alert-list"' in response.text
    assert 'id="operational-history-list"' in response.text
    assert 'id="operational-self-test"' in response.text
    assert 'id="history-card"' in response.text
    assert 'id="quality-feedback-total"' in response.text
    assert 'id="feedback-dialog"' in response.text
    assert 'id="regression-dialog"' in response.text
    assert 'id="regression-list"' in response.text
    assert 'class="regression-status-row"' in response.text
    assert 'class="row panel-actions"' in response.text
    assert 'href="/admin-assets/admin.css?v=admin-modules-2"' in response.text
    assert (
        'type="module" src="/admin-assets/js/app.js?v=admin-modules-2"'
        in response.text
    )
    assert 'id="image_search_provider"' in response.text
    assert 'id="vision_provider"' in response.text
    assert 'id="vision_model"' in response.text
    assert 'id="vision_max_image_mb"' in response.text
    assert 'id="stt_base_url"' in response.text
    assert 'id="tts_base_url"' in response.text
    assert 'id="stt_api_key"' in response.text
    assert 'id="tts_api_key"' in response.text
    assert 'id="clear_stt_api_key"' in response.text
    assert 'id="clear_tts_api_key"' in response.text
    assert 'id="agent-tool-image-search"' in response.text
    assert 'id="agent-tool-image-understanding"' in response.text
    assert 'id="pipeline-vision"' in response.text
    assert 'id="safety-baseline-save"' in response.text
    assert 'id="gateway-restart"' in response.text
    assert 'id="config-revision-list"' in response.text
    assert 'id="config-preview-dialog"' in response.text
    assert 'id="config-preview-apply"' in response.text
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
        memory = await client.get("/admin-assets/js/memory-screen.js")
        infrastructure = await client.get(
            "/admin-assets/js/infrastructure-screen.js"
        )
        quality = await client.get("/admin-assets/js/quality-screen.js")

    assert css.status_code == 200
    assert css.headers["cache-control"] == "no-cache, must-revalidate"
    assert "@media (max-width: 820px)" in css.text
    assert ".grid.three { grid-template-columns: repeat(3" in css.text
    assert '.option-row input[type="checkbox"]' in css.text
    assert app.status_code == 200
    assert 'from "./api-client.js?v=admin-modules-2"' in app.text
    assert "restoreBrowserSession()" in app.text
    assert navigation.status_code == 200
    assert safety.status_code == 200
    assert history.status_code == 200
    assert memory.status_code == 200
    assert infrastructure.status_code == 200
    assert infrastructure.headers["cache-control"] == "no-cache, must-revalidate"
    assert 'byId("operational-self-test").onclick = runAlertSelfTest' in infrastructure.text
    assert "/api/infrastructure/scan" in infrastructure.text
    assert "/acknowledge" in infrastructure.text
    assert "/alerts/self-test" in infrastructure.text
    assert "/api/settings/preview" in app.text
    assert "/api/settings/revisions" in app.text
    assert quality.status_code == 200
    assert "/api/quality/feedback" in quality.text
    assert "regression-cases" in quality.text
    assert 'actions.className = "row card-actions"' in quality.text
    assert "@media (max-width: 1100px)" in css.text
    assert ".regression-status-row" in css.text
    tab_rule = css.text.split(".tab-button {", 1)[1].split("}", 1)[0]
    assert "display: flex" in tab_rule
    assert "justify-content: center" not in tab_rule


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
        assert body["vision_provider"] in {"disabled", "openai_compatible"}
        assert "vision_api_key" not in body
        assert "vision_api_key_preview" in body
        assert "stt_base_url" in body
        assert "tts_base_url" in body
        assert "stt_api_key" not in body
        assert "tts_api_key" not in body
        assert "stt_api_key_preview" in body
        assert "tts_api_key_preview" in body
    finally:
        admin_app.dependency_overrides.clear()
