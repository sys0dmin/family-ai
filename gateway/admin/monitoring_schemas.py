"""Validated response contracts for protected infrastructure monitoring."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

HealthStatus = Literal["healthy", "degraded", "down", "unconfigured"]


class ResourceUsage(BaseModel):
    """Current usage for a byte-addressable resource."""

    used_bytes: int
    total_bytes: int
    percent: float


class NodeStatus(BaseModel):
    """Normalized Linux container health returned to the Admin UI."""

    id: str
    name: str
    role: str
    status: HealthStatus
    uptime_seconds: int | None = None
    cpu_percent: float | None = None
    cpu_cores: int | None = None
    load1: float | None = None
    memory: ResourceUsage | None = None
    disk: ResourceUsage | None = None
    scrape_latency_ms: float | None = None
    message: str | None = None


class DatabaseStatus(BaseModel):
    """PostgreSQL application-level health and capacity."""

    status: HealthStatus
    latency_ms: float | None = None
    uptime_seconds: int | None = None
    version: str | None = None
    size_bytes: int | None = None
    connections: int | None = None
    max_connections: int | None = None
    message: str | None = None


class InfrastructureStatusResponse(BaseModel):
    """Single protected snapshot for the project infrastructure."""

    status: HealthStatus
    checked_at: datetime
    nodes: list[NodeStatus]
    database: DatabaseStatus
