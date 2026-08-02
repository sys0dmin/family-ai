"""Tests for protected project infrastructure monitoring."""

from urllib.error import URLError

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from gateway.admin.auth import verify_admin
from gateway.admin.main import app as admin_app
from gateway.admin.monitoring_router import get_infrastructure_monitoring_service
from gateway.admin.monitoring_schemas import (
    DatabaseStatus,
    InfrastructureStatusResponse,
    NodeStatus,
    ResourceUsage,
)
from gateway.admin.monitoring_service import (
    DatabaseCollector,
    InfrastructureMonitoringService,
    NodeExporterCollector,
    parse_prometheus_text,
)
from gateway.admin.operational_alert_service import OperationalAlertService
from gateway.admin.voice_observability_schemas import (
    MetricsSource,
    VoiceObservabilityResponse,
)
from gateway.app.config import Settings

NODE_METRICS = """
# HELP node_cpu_seconds_total Seconds the CPUs spent in each mode.
node_cpu_seconds_total{cpu="0",mode="idle"} 80
node_cpu_seconds_total{cpu="0",mode="user"} 20
node_cpu_seconds_total{cpu="1",mode="idle"} 90
node_cpu_seconds_total{cpu="1",mode="user"} 10
node_load1 0.5
node_memory_MemTotal_bytes 1000
node_memory_MemAvailable_bytes 400
node_filesystem_size_bytes{device="/dev/vda1",fstype="ext4",mountpoint="/"} 2000
node_filesystem_avail_bytes{device="/dev/vda1",fstype="ext4",mountpoint="/"} 500
node_boot_time_seconds 100
"""


def test_prometheus_parser_preserves_labels_and_values() -> None:
    samples = parse_prometheus_text(NODE_METRICS)

    filesystem = next(sample for sample in samples if sample.name.endswith("size_bytes"))
    assert filesystem.labels["mountpoint"] == "/"
    assert filesystem.labels["fstype"] == "ext4"
    assert filesystem.value == 2000


def test_node_collector_normalizes_linux_resources(monkeypatch) -> None:
    monkeypatch.setattr("gateway.admin.monitoring_service.time.time", lambda: 1100)
    collector = NodeExporterCollector(fetcher=lambda _url, _timeout: NODE_METRICS)

    result = collector.collect(
        node_id="gateway",
        name="family-ai-gateway",
        role="AI Gateway",
        url="http://metrics",
        timeout_seconds=1,
    )

    assert result.status == "healthy"
    assert result.cpu_cores == 2
    assert result.cpu_percent == 25.0
    assert result.uptime_seconds == 1000
    assert result.memory == ResourceUsage(used_bytes=600, total_bytes=1000, percent=60)
    assert result.disk == ResourceUsage(used_bytes=1500, total_bytes=2000, percent=75)


def test_node_collector_hides_transport_errors() -> None:
    def unavailable(_url: str, _timeout: float) -> str:
        raise URLError("private network details")

    result = NodeExporterCollector(fetcher=unavailable).collect(
        node_id="database",
        name="family-ai-db",
        role="PostgreSQL",
        url="http://metrics",
        timeout_seconds=1,
    )

    assert result.status == "down"
    assert result.message == "Metrics endpoint is unavailable"
    assert "private" not in result.message


def test_database_collector_supports_development_database(db_session: Session) -> None:
    result = DatabaseCollector().collect(db_session)

    assert result.status == "healthy"
    assert result.version == "sqlite (development)"
    assert result.latency_ms is not None


def test_monitoring_service_collects_all_project_nodes(db_session: Session) -> None:
    class StubNodeCollector:
        def __init__(self) -> None:
            self.node_ids: list[str] = []

        def collect(self, **kwargs) -> NodeStatus:
            self.node_ids.append(kwargs["node_id"])
            return NodeStatus(
                id=kwargs["node_id"],
                name=kwargs["name"],
                role=kwargs["role"],
                status="healthy",
            )

    class StubDatabaseCollector:
        def collect(self, _session: Session) -> DatabaseStatus:
            return DatabaseStatus(status="healthy")

    node_collector = StubNodeCollector()
    service = InfrastructureMonitoringService(
        settings=Settings(
            gateway_node_metrics_url="http://gateway/metrics",
            database_node_metrics_url="http://database/metrics",
            speech_node_metrics_url="http://speech/metrics",
        ),
        session=db_session,
        node_collector=node_collector,
        database_collector=StubDatabaseCollector(),
    )

    result = service.get_status()

    assert result.status == "healthy"
    assert node_collector.node_ids == ["gateway", "database", "speech"]


@pytest.mark.anyio
async def test_infrastructure_api_requires_authentication() -> None:
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://admin") as client:
        response = await client.get("/api/infrastructure")

    assert response.status_code == 401


@pytest.mark.anyio
async def test_operational_scan_requires_authentication() -> None:
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://admin") as client:
        response = await client.post("/api/infrastructure/scan")

    assert response.status_code == 401


@pytest.mark.anyio
async def test_infrastructure_api_returns_normalized_snapshot() -> None:
    class StubService:
        def get_status(self) -> InfrastructureStatusResponse:
            return InfrastructureStatusResponse(
                status="healthy",
                checked_at="2026-07-18T12:00:00Z",
                nodes=[
                    NodeStatus(
                        id="gateway",
                        name="family-ai-gateway",
                        role="AI Gateway",
                        status="healthy",
                    )
                ],
                database=DatabaseStatus(status="healthy", latency_ms=1.2),
            )

    admin_app.dependency_overrides[verify_admin] = lambda: "admin"
    admin_app.dependency_overrides[get_infrastructure_monitoring_service] = StubService
    try:
        transport = ASGITransport(app=admin_app)
        async with AsyncClient(transport=transport, base_url="http://admin") as client:
            response = await client.get("/api/infrastructure")
    finally:
        admin_app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["nodes"][0]["id"] == "gateway"
    assert response.json()["database"]["latency_ms"] == 1.2


def _infrastructure_snapshot(*, disk_used_percent: float | None = None):
    disk = None
    if disk_used_percent is not None:
        disk = ResourceUsage(
            used_bytes=int(disk_used_percent * 10),
            total_bytes=1000,
            percent=disk_used_percent,
        )
    return InfrastructureStatusResponse(
        status="healthy",
        checked_at="2026-08-02T12:00:00Z",
        nodes=[
            NodeStatus(
                id="speech",
                name="family-ai-speech",
                role="Local STT · TTS",
                status="healthy",
                disk=disk,
            )
        ],
        database=DatabaseStatus(status="healthy"),
    )


def _voice_snapshot(*, queue_depth: int = 0, recent: list[dict] | None = None):
    return VoiceObservabilityResponse(
        gateway=MetricsSource(status="healthy", data={"recent": recent or []}),
        speech=MetricsSource(status="healthy", data={"queue_depth": queue_depth}),
    )


def test_operational_alert_lifecycle_keeps_acknowledged_technical_history(
    db_session: Session,
) -> None:
    service = OperationalAlertService(db_session, Settings())

    active = service.reconcile(
        _infrastructure_snapshot(disk_used_percent=86),
        _voice_snapshot(queue_depth=2),
    )

    assert {item.metric for item in active.active} == {"disk_free_percent", "queue_depth"}
    disk_alert = next(item for item in active.active if item.metric == "disk_free_percent")
    acknowledged = service.acknowledge(disk_alert.id, "parent-admin")
    assert acknowledged is not None
    assert acknowledged.acknowledged_by == "parent-admin"

    recovered = service.reconcile(
        _infrastructure_snapshot(disk_used_percent=50),
        _voice_snapshot(queue_depth=0),
    )

    assert recovered.active == []
    assert len(recovered.history) == 2
    restored_disk = next(item for item in recovered.history if item.metric == "disk_free_percent")
    assert restored_disk.acknowledged_at is not None
    assert restored_disk.resolved_at is not None


def test_operational_alert_uses_only_allowlisted_voice_error_counts(
    db_session: Session,
) -> None:
    service = OperationalAlertService(db_session, Settings())
    recent = [
        {
            "status": "error",
            "error_stage": "tts",
            "private_text": "sensitive child content",
            "turn_id": "conversation-identifier",
        }
        for _ in range(3)
    ]

    result = service.reconcile(
        _infrastructure_snapshot(),
        _voice_snapshot(recent=recent),
    )

    assert len(result.active) == 1
    alert = result.active[0]
    assert alert.metric == "voice_error_streak"
    assert alert.current_value == 3
    assert "sensitive" not in alert.detail
    assert "conversation" not in alert.detail
