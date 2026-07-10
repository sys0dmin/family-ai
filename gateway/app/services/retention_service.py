"""Message retention policy."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from gateway.app.models import Message


class RetentionService:
    """Apply the configured transcript retention window."""

    def __init__(self, session: Session, retention_days: int) -> None:
        self._session = session
        self._retention_days = retention_days

    def purge_expired_messages(self, *, now: datetime | None = None) -> int:
        """Delete messages older than the retention window."""

        current_time = now or datetime.now(UTC)
        cutoff = current_time - timedelta(days=self._retention_days)
        result = self._session.execute(delete(Message).where(Message.created_at < cutoff))
        self._session.flush()
        return result.rowcount or 0
