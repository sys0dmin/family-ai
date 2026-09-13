"""Short-lived state for one deterministic pretend-clinic game."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gateway.app.db.base import Base

if TYPE_CHECKING:
    from gateway.app.models.conversation import Conversation


class ClinicSession(Base):
    __tablename__ = "clinic_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'paused', 'completed', 'left')", name="ck_clinic_sessions_status"
        ),
        Index("ix_clinic_sessions_status_expires", "status", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    case_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    case_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    vital_snapshot: Mapped[dict[str, dict[str, str]]] = mapped_column(JSON, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="clinic_session")
    procedure_events: Mapped[list["ClinicProcedureEvent"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ClinicProcedureEvent.created_at",
    )


class ClinicProcedureEvent(Base):
    __tablename__ = "clinic_procedure_events"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "action_id",
            name="uq_clinic_event_action",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clinic_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_id: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped[ClinicSession] = relationship(back_populates="procedure_events")
