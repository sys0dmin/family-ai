"""Collectors and aggregation for the two Family AI runtime containers."""

from __future__ import annotations

import math
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from gateway.admin.monitoring_schemas import (
    DatabaseStatus,
    HealthStatus,
    InfrastructureStatusResponse,
    NodeStatus,
    ResourceUsage,
)
from gateway.app.config import Settings

_SAMPLE_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(?P<labels>[^}]*)\})?\s+"
    r"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|NaN|[+-]Inf)"
)
_LABEL_RE = re.compile(r'(\w+)="((?:\\.|[^"\\])*)"')
_STATUS_PRIORITY: dict[HealthStatus, int] = {
    "healthy": 0,
    "unconfigured": 1,
    "degraded": 2,
    "down": 3,
}


@dataclass(frozen=True)
class MetricSample:
    """One parsed Prometheus exposition sample."""

    name: str
    labels: dict[str, str]
    value: float


@dataclass(frozen=True)
class _CpuCounters:
    idle: float
    total: float


MetricsFetcher = Callable[[str, float], str]


def _fetch_metrics(url: str, timeout_seconds: float) -> str:
    request = Request(url, headers={"Accept": "text/plain"})
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        return response.read().decode("utf-8", errors="replace")


def parse_prometheus_text(payload: str) -> list[MetricSample]:
    """Parse the subset of the Prometheus text format used by node_exporter."""

    samples: list[MetricSample] = []
    for raw_line in payload.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _SAMPLE_RE.match(line)
        if not match:
            continue
        value = float(match.group("value"))
        if not math.isfinite(value):
            continue
        labels = {
            label_match.group(1): bytes(label_match.group(2), "utf-8")
            .decode("unicode_escape")
            for label_match in _LABEL_RE.finditer(match.group("labels") or "")
        }
        samples.append(MetricSample(match.group("name"), labels, value))
    return samples


def _single_value(samples: list[MetricSample], name: str) -> float | None:
    return next((sample.value for sample in samples if sample.name == name), None)


def _usage(used_bytes: float, total_bytes: float) -> ResourceUsage | None:
    if total_bytes <= 0:
        return None
    used = max(0, min(int(used_bytes), int(total_bytes)))
    total = int(total_bytes)
    return ResourceUsage(
        used_bytes=used,
        total_bytes=total,
        percent=round(used / total * 100, 1),
    )


class NodeExporterCollector:
    """Collect and normalize current Linux metrics from node_exporter."""

    def __init__(self, fetcher: MetricsFetcher = _fetch_metrics) -> None:
        self._fetcher = fetcher
        self._cpu_samples: dict[str, _CpuCounters] = {}
        self._lock = threading.Lock()

    def collect(
        self,
        *,
        node_id: str,
        name: str,
        role: str,
        url: str | None,
        timeout_seconds: float,
    ) -> NodeStatus:
        if not url:
            return NodeStatus(
                id=node_id,
                name=name,
                role=role,
                status="unconfigured",
                message="Metrics endpoint is not configured",
            )

        started = time.perf_counter()
        try:
            samples = parse_prometheus_text(self._fetcher(url, timeout_seconds))
        except (HTTPError, URLError, OSError, TimeoutError, ValueError):
            return NodeStatus(
                id=node_id,
                name=name,
                role=role,
                status="down",
                message="Metrics endpoint is unavailable",
            )

        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        memory_total = _single_value(samples, "node_memory_MemTotal_bytes")
        memory_available = _single_value(samples, "node_memory_MemAvailable_bytes")
        memory = None
        if memory_total is not None and memory_available is not None:
            memory = _usage(memory_total - memory_available, memory_total)

        root_samples = [
            sample
            for sample in samples
            if sample.name in {"node_filesystem_size_bytes", "node_filesystem_avail_bytes"}
            and sample.labels.get("mountpoint") == "/"
            and sample.labels.get("fstype") not in {"tmpfs", "overlay", "squashfs"}
        ]
        disk_size = next(
            (sample.value for sample in root_samples if sample.name.endswith("size_bytes")),
            None,
        )
        disk_available = next(
            (sample.value for sample in root_samples if sample.name.endswith("avail_bytes")),
            None,
        )
        disk = None
        if disk_size is not None and disk_available is not None:
            disk = _usage(disk_size - disk_available, disk_size)

        cpu_samples = [sample for sample in samples if sample.name == "node_cpu_seconds_total"]
        cores = len({sample.labels.get("cpu") for sample in cpu_samples}) or None
        load1 = _single_value(samples, "node_load1")
        cpu_percent = self._cpu_percent(node_id, cpu_samples, load1, cores)
        boot_time = _single_value(samples, "node_boot_time_seconds")
        uptime_seconds = max(0, int(time.time() - boot_time)) if boot_time else None

        status: HealthStatus = "healthy"
        if any(
            value is not None and value >= 90
            for value in (
                cpu_percent,
                memory.percent if memory else None,
                disk.percent if disk else None,
            )
        ):
            status = "degraded"

        return NodeStatus(
            id=node_id,
            name=name,
            role=role,
            status=status,
            uptime_seconds=uptime_seconds,
            cpu_percent=cpu_percent,
            cpu_cores=cores,
            load1=round(load1, 2) if load1 is not None else None,
            memory=memory,
            disk=disk,
            scrape_latency_ms=latency_ms,
        )

    def _cpu_percent(
        self,
        node_id: str,
        samples: list[MetricSample],
        load1: float | None,
        cores: int | None,
    ) -> float | None:
        total = sum(sample.value for sample in samples)
        idle = sum(
            sample.value
            for sample in samples
            if sample.labels.get("mode") in {"idle", "iowait"}
        )
        current = _CpuCounters(idle=idle, total=total)
        with self._lock:
            previous = self._cpu_samples.get(node_id)
            self._cpu_samples[node_id] = current

        if previous and current.total > previous.total:
            total_delta = current.total - previous.total
            idle_delta = max(0.0, current.idle - previous.idle)
            return round(max(0.0, min(100.0, (1 - idle_delta / total_delta) * 100)), 1)
        if load1 is not None and cores:
            return round(max(0.0, min(100.0, load1 / cores * 100)), 1)
        return None


class DatabaseCollector:
    """Collect application-relevant PostgreSQL health through the existing session."""

    def collect(self, session: Session) -> DatabaseStatus:
        started = time.perf_counter()
        try:
            dialect = session.get_bind().dialect.name
            if dialect == "postgresql":
                row = session.execute(
                    text(
                        """
                        SELECT version(),
                               EXTRACT(EPOCH FROM (now() - pg_postmaster_start_time())),
                               pg_database_size(current_database()),
                               (SELECT count(*) FROM pg_stat_activity),
                               current_setting('max_connections')::int
                        """
                    )
                ).one()
                version, uptime, size_bytes, connections, max_connections = row
            else:
                version = f"{dialect} (development)"
                session.execute(text("SELECT 1")).scalar_one()
                uptime = size_bytes = connections = max_connections = None
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
        except SQLAlchemyError:
            session.rollback()
            return DatabaseStatus(status="down", message="Database query failed")

        status: HealthStatus = "healthy"
        if connections is not None and max_connections and connections / max_connections >= 0.8:
            status = "degraded"
        return DatabaseStatus(
            status=status,
            latency_ms=latency_ms,
            uptime_seconds=int(uptime) if uptime is not None else None,
            version=str(version).split(" on ", 1)[0],
            size_bytes=int(size_bytes) if size_bytes is not None else None,
            connections=int(connections) if connections is not None else None,
            max_connections=int(max_connections) if max_connections is not None else None,
        )


class InfrastructureMonitoringService:
    """Aggregate node and database health behind a stable Admin API."""

    def __init__(
        self,
        *,
        settings: Settings,
        session: Session,
        node_collector: NodeExporterCollector,
        database_collector: DatabaseCollector | None = None,
    ) -> None:
        self._settings = settings
        self._session = session
        self._node_collector = node_collector
        self._database_collector = database_collector or DatabaseCollector()

    def get_status(self) -> InfrastructureStatusResponse:
        timeout = self._settings.monitoring_request_timeout_seconds
        nodes = [
            self._node_collector.collect(
                node_id="gateway",
                name="family-ai-gateway",
                role="AI Gateway · Admin · Voice",
                url=self._settings.gateway_node_metrics_url,
                timeout_seconds=timeout,
            ),
            self._node_collector.collect(
                node_id="database",
                name="family-ai-db",
                role="PostgreSQL · History",
                url=self._settings.database_node_metrics_url,
                timeout_seconds=timeout,
            ),
        ]
        database = self._database_collector.collect(self._session)
        statuses = [node.status for node in nodes] + [database.status]
        overall = max(statuses, key=_STATUS_PRIORITY.__getitem__)
        return InfrastructureStatusResponse(
            status=overall,
            checked_at=datetime.now(UTC),
            nodes=nodes,
            database=database,
        )
