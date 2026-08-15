"""Privacy and API tests for bounded technical request traces."""

from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.admin.auth import verify_admin
from gateway.admin.diagnostics_router import get_trace_registry
from gateway.admin.main import app as admin_app
from gateway.app.observability.request_tracing import RequestTraceRegistry


def test_registry_keeps_only_structured_allowlisted_events() -> None:
    registry = RequestTraceRegistry(max_traces=2)
    request_id = uuid4()

    registry.start(request_id, "voice")
    registry.event(request_id, "stt", "success", duration_ms=120)
    registry.finish(request_id, "error", error_code="tts")
    registry.finish(request_id, "error", error_code="duplicate")

    trace = registry.get(request_id)
    assert trace is not None
    assert trace.status == "error"
    assert [event.stage for event in trace.events] == ["request", "stt", "request"]
    assert trace.events[-1].error_code == "tts"
    assert not hasattr(trace, "message")
    assert not hasattr(trace.events[0], "content")


def test_file_registry_is_shared_between_gateway_and_admin_processes(
    tmp_path: Path,
) -> None:
    database_path = str(tmp_path / "traces.sqlite3")
    gateway_registry = RequestTraceRegistry(database_path=database_path)
    admin_registry = RequestTraceRegistry(database_path=database_path)
    request_id = uuid4()

    gateway_registry.start(request_id, "voice")
    gateway_registry.event(request_id, "stt", "error", error_code="no_speech")
    gateway_registry.finish(request_id, "error", error_code="stt")

    trace = admin_registry.get(request_id)
    assert trace is not None
    assert trace.status == "error"
    assert [event.stage for event in trace.events] == ["request", "stt", "request"]


@pytest.mark.anyio
async def test_admin_exports_redacted_diagnostic_bundle() -> None:
    registry = RequestTraceRegistry()
    request_id = uuid4()
    registry.start(request_id, "multimodal")
    registry.event(
        request_id,
        "vision",
        "error",
        duration_ms=42,
        error_code="provider_error",
    )
    registry.finish(request_id, "error", error_code="vision")

    admin_app.dependency_overrides[verify_admin] = lambda: "admin"
    admin_app.dependency_overrides[get_trace_registry] = lambda: registry
    try:
        transport = ASGITransport(app=admin_app)
        async with AsyncClient(transport=transport, base_url="http://admin") as client:
            traces = await client.get("/api/diagnostics/traces")
            bundle = await client.get("/api/diagnostics/bundle")
    finally:
        admin_app.dependency_overrides.clear()

    assert traces.status_code == 200
    assert traces.json()[0]["request_id"] == str(request_id)
    assert bundle.status_code == 200
    assert bundle.headers["cache-control"] == "no-store"
    payload = bundle.json()
    assert payload["privacy"] == {
        "contains_messages": False,
        "contains_audio": False,
        "contains_images": False,
        "contains_secrets": False,
    }
    serialized = bundle.text.lower()
    assert "api_key" not in serialized
    assert "audio_content" not in serialized
    assert "image_content" not in serialized
