"""Versioned global child-safety prompt configuration."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gateway.app.db.base import Base


class SafetyBaselineRevision(Base):
    """Immutable revision of the prompt-level child-safety baseline."""

    __tablename__ = "safety_baseline_revisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SafetyBaselineConfiguration(Base):
    """Singleton pointer to the currently published baseline revision."""

    __tablename__ = "safety_baseline_configuration"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_safety_baseline_configuration_singleton"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    active_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("safety_baseline_revisions.id"),
    )
    active_revision: Mapped[SafetyBaselineRevision | None] = relationship(
        foreign_keys=[active_revision_id],
    )
