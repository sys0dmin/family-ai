"""Short-lived state for one configured activity in a conversation."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gateway.app.db.base import Base

if TYPE_CHECKING:
    from gateway.app.models.conversation import Conversation


class ActivitySession(Base):
    __tablename__ = "activity_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed', 'cancelled', 'left')",
            name="ck_activity_sessions_status",
        ),
        CheckConstraint("current_step >= 0", name="ck_activity_sessions_step"),
        Index("ix_activity_sessions_status_expires", "status", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    activity_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    activity_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="activity_session")
