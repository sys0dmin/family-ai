"""Message retention policy."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from gateway.app.models import Message, MessageFeedback, RegressionCase


class RetentionService:
    """Apply the configured transcript retention window."""

    def __init__(self, session: Session, retention_days: int) -> None:
        self._session = session
        self._retention_days = retention_days

    def purge_expired_messages(self, *, now: datetime | None = None) -> int:
        """Delete messages older than the retention window."""

        current_time = now or datetime.now(UTC)
        cutoff = current_time - timedelta(days=self._retention_days)
        expired_message_ids = select(Message.id).where(Message.created_at < cutoff)
        expired_feedback_ids = select(MessageFeedback.id).where(
            MessageFeedback.message_id.in_(expired_message_ids)
        )
        self._session.execute(
            update(RegressionCase)
            .where(RegressionCase.source_feedback_id.in_(expired_feedback_ids))
            .values(source_feedback_id=None)
        )
        self._session.execute(
            delete(MessageFeedback).where(
                MessageFeedback.message_id.in_(expired_message_ids)
            )
        )
        result = self._session.execute(delete(Message).where(Message.created_at < cutoff))
        self._session.flush()
        return result.rowcount or 0
