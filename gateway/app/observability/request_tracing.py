"""Bounded privacy-safe technical traces for recent application turns."""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TraceEvent:
    occurred_at: datetime
    stage: str
    status: str
    duration_ms: int | None = None
    error_code: str | None = None
    service: str = "gateway"


@dataclass
class RequestTrace:
    request_id: UUID
    mode: str
    started_at: datetime
    status: str = "running"
    completed_at: datetime | None = None
    events: list[TraceEvent] = field(default_factory=list)


class RequestTraceRegistry:
    """Store only allowlisted technical fields in a small SQLite repository."""

    def __init__(
        self,
        max_traces: int = 200,
        retention_hours: int = 24,
        database_path: str = ":memory:",
    ) -> None:
        self._max_traces = max_traces
        self._retention = timedelta(hours=retention_hours)
        self._lock = threading.RLock()
        if database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            database_path,
            check_same_thread=False,
            timeout=5,
        )
        self._connection.row_factory = sqlite3.Row
        with self._connection:
            self._connection.execute("PRAGMA foreign_keys = ON")
            if database_path != ":memory:":
                self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS request_traces (
                    request_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS trace_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL REFERENCES request_traces(request_id)
                        ON DELETE CASCADE,
                    occurred_at TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_ms INTEGER,
                    error_code TEXT,
                    service TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_request_traces_started_at
                    ON request_traces(started_at);
                CREATE INDEX IF NOT EXISTS ix_trace_events_request_id
                    ON trace_events(request_id, id);
                """
            )

    @staticmethod
    def request_id(value: UUID | None = None) -> UUID:
        return value or uuid4()

    def start(self, request_id: UUID, mode: str) -> None:
        now = datetime.now(UTC)
        with self._lock, self._connection:
            self._prune_locked(now)
            self._connection.execute(
                """
                INSERT INTO request_traces
                    (request_id, mode, started_at, status, completed_at)
                VALUES (?, ?, ?, 'running', NULL)
                ON CONFLICT(request_id) DO UPDATE SET
                    mode = excluded.mode,
                    started_at = excluded.started_at,
                    status = 'running',
                    completed_at = NULL
                """,
                (str(request_id), mode, now.isoformat()),
            )
            self._connection.execute(
                "DELETE FROM trace_events WHERE request_id = ?",
                (str(request_id),),
            )
            self._trim_locked()
        self.event(request_id, "request", "started")

    def event(
        self,
        request_id: UUID,
        stage: str,
        status: str,
        *,
        duration_ms: int | None = None,
        error_code: str | None = None,
        service: str = "gateway",
    ) -> None:
        occurred_at = datetime.now(UTC)
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO trace_events
                    (request_id, occurred_at, stage, status, duration_ms,
                     error_code, service)
                SELECT ?, ?, ?, ?, ?, ?, ?
                WHERE EXISTS (
                    SELECT 1 FROM request_traces WHERE request_id = ?
                )
                """,
                (
                    str(request_id),
                    occurred_at.isoformat(),
                    stage,
                    status,
                    duration_ms,
                    error_code,
                    service,
                    str(request_id),
                ),
            )
        if cursor.rowcount == 0:
            return
        logger.info(
            "technical_trace_event",
            extra={
                "request_id": str(request_id),
                "trace_stage": stage,
                "trace_status": status,
                "duration_ms": duration_ms,
                "error_code": error_code,
                "trace_service": service,
            },
        )

    def finish(
        self,
        request_id: UUID,
        status: str,
        *,
        error_code: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT started_at, status FROM request_traces WHERE request_id = ?",
                (str(request_id),),
            ).fetchone()
            if row is None or row["status"] != "running":
                return
            started_at = datetime.fromisoformat(row["started_at"])
            self._connection.execute(
                """
                UPDATE request_traces
                SET status = ?, completed_at = ?
                WHERE request_id = ?
                """,
                (status, now.isoformat(), str(request_id)),
            )
        duration_ms = round((now - started_at).total_seconds() * 1000)
        self.event(
            request_id,
            "request",
            status,
            duration_ms=duration_ms,
            error_code=error_code,
        )

    def list(self, *, failed_only: bool = False) -> list[RequestTrace]:
        now = datetime.now(UTC)
        with self._lock, self._connection:
            self._prune_locked(now)
            where = "WHERE status IN ('error', 'cancelled')" if failed_only else ""
            rows = self._connection.execute(
                f"""
                SELECT request_id, mode, started_at, status, completed_at
                FROM request_traces {where}
                ORDER BY started_at DESC
                """  # noqa: S608 - the clause is an internal constant
            ).fetchall()
            return [self._hydrate(row) for row in rows]

    def get(self, request_id: UUID) -> RequestTrace | None:
        now = datetime.now(UTC)
        with self._lock, self._connection:
            self._prune_locked(now)
            row = self._connection.execute(
                """
                SELECT request_id, mode, started_at, status, completed_at
                FROM request_traces WHERE request_id = ?
                """,
                (str(request_id),),
            ).fetchone()
            return self._hydrate(row) if row else None

    def clear(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM request_traces")

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _prune_locked(self, now: datetime) -> None:
        cutoff = (now - self._retention).isoformat()
        self._connection.execute(
            "DELETE FROM request_traces WHERE started_at < ?",
            (cutoff,),
        )

    def _trim_locked(self) -> None:
        self._connection.execute(
            """
            DELETE FROM request_traces
            WHERE request_id IN (
                SELECT request_id FROM request_traces
                ORDER BY started_at DESC
                LIMIT -1 OFFSET ?
            )
            """,
            (self._max_traces,),
        )

    def _hydrate(self, row: sqlite3.Row) -> RequestTrace:
        event_rows = self._connection.execute(
            """
            SELECT occurred_at, stage, status, duration_ms, error_code, service
            FROM trace_events WHERE request_id = ? ORDER BY id
            """,
            (row["request_id"],),
        ).fetchall()
        return RequestTrace(
            request_id=UUID(row["request_id"]),
            mode=row["mode"],
            started_at=datetime.fromisoformat(row["started_at"]),
            status=row["status"],
            completed_at=(
                datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None
            ),
            events=[
                TraceEvent(
                    occurred_at=datetime.fromisoformat(event["occurred_at"]),
                    stage=event["stage"],
                    status=event["status"],
                    duration_ms=event["duration_ms"],
                    error_code=event["error_code"],
                    service=event["service"],
                )
                for event in event_rows
            ],
        )


request_trace_registry = RequestTraceRegistry(
    database_path=os.getenv("FAMILY_AI_TRACE_DB_PATH", ":memory:")
)
