"""Parent-confirmed long-term memory ORM model."""

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gateway.app.db.base import Base

if TYPE_CHECKING:
    from gateway.app.models.child_profile import ChildProfile


class MemoryCategory(StrEnum):
    """Supported kinds of durable child information."""

    INTEREST = "interest"
    PREFERENCE = "preference"
    LEARNING_PROGRESS = "learning_progress"


class MemorySourceType(StrEnum):
    """Parent-selected origin of a confirmed memory."""

    PARENT_OBSERVATION = "parent_observation"
    CHILD_STATEMENT = "child_statement"
    LEARNING_ACTIVITY = "learning_activity"


class LongTermMemory(Base):
    """One structured fact explicitly confirmed by a parent."""

    __tablename__ = "long_term_memories"
    __table_args__ = (
        CheckConstraint(
            "category IN ('interest', 'preference', 'learning_progress')",
            name="ck_long_term_memories_category",
        ),
        CheckConstraint(
            "source_type IN "
            "('parent_observation', 'child_statement', 'learning_activity')",
            name="ck_long_term_memories_source_type",
        ),
        Index(
            "ix_long_term_memories_profile_category_updated",
            "child_profile_id",
            "category",
            "updated_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    child_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("child_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    topic: Mapped[str] = mapped_column(String(120), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_note: Mapped[str | None] = mapped_column(String(500))
    source_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    child_profile: Mapped["ChildProfile"] = relationship(back_populates="memories")
