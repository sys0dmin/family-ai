"""Tests for public operational endpoints."""

import httpx
import pytest

from gateway.app.main import app


@pytest.mark.anyio
async def test_healthcheck_returns_ready_status() -> None:
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "ai-gateway"}
