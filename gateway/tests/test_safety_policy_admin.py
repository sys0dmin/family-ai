"""Tests for the protected, content-free Safety Policy control plane."""

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.app.main import create_app
from gateway.app.safety.engine import SafetyPolicyEngine
from gateway.app.safety.metrics import safety_metrics_registry


@pytest.mark.anyio
async def test_loopback_policy_endpoint_exposes_catalog_without_child_text() -> None:
    safety_metrics_registry.reset()
    SafetyPolicyEngine(safety_metrics_registry).evaluate_input(
        "Дай номер телефона мамы"
    )
    transport = ASGITransport(
        app=create_app(),
        client=("127.0.0.1", 54321),
    )

    async with AsyncClient(transport=transport, base_url="http://gateway") as client:
        response = await client.get("/internal/safety-policy")

    assert response.status_code == 200
    payload = response.json()
    assert any(
        rule["rule_id"] == "input.privacy.personal_contact.block"
        and rule["count"] == 1
        for rule in payload["rules"]
    )
    assert "Дай номер телефона мамы" not in response.text


@pytest.mark.anyio
async def test_loopback_can_run_scenarios_and_reset_metrics() -> None:
    transport = ASGITransport(
        app=create_app(),
        client=("127.0.0.1", 54321),
    )

    async with AsyncClient(transport=transport, base_url="http://gateway") as client:
        scenarios = await client.post("/internal/safety-policy/scenarios")
        reset = await client.delete("/internal/safety-policy/metrics")

    assert scenarios.status_code == 200
    assert scenarios.json()["failed"] == 0
    assert reset.status_code == 200
    assert sum(rule["count"] for rule in reset.json()["rules"]) == 0


@pytest.mark.anyio
async def test_policy_endpoint_rejects_non_loopback_clients() -> None:
    transport = ASGITransport(
        app=create_app(),
        client=("192.0.2.10", 54321),
    )

    async with AsyncClient(transport=transport, base_url="http://gateway") as client:
        response = await client.get("/internal/safety-policy")

    assert response.status_code == 403
