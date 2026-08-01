"""Parent-controlled quality feedback and regression cases."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
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
    from gateway.app.models.agent import Agent
    from gateway.app.models.message import Message


class FeedbackReason(StrEnum):
    """Stable parent-facing categories used for aggregate quality metrics."""

    FACTUAL_ERROR = "factual_error"
    MISUNDERSTOOD = "misunderstood"
    TOO_COMPLEX = "too_complex"
    FALSE_BLOCK = "false_block"
    CHARACTER_BREAK = "character_break"
    BAD_VOICE = "bad_voice"
    BAD_VISION = "bad_vision"
    OTHER = "other"


class MessageFeedback(Base):
    """Short-lived evaluation owned by one retained message."""

    __tablename__ = "message_feedback"
    __table_args__ = (
        CheckConstraint(
            "reason IN ('factual_error', 'misunderstood', 'too_complex', "
            "'false_block', 'character_break', 'bad_voice', 'bad_vision', 'other')",
            name="ck_message_feedback_reason",
        ),
        Index("ix_message_feedback_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    reason: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    message: Mapped["Message"] = relationship(back_populates="feedback")
    regression_cases: Mapped[list["RegressionCase"]] = relationship(
        back_populates="source_feedback",
    )


class RegressionCase(Base):
    """Explicitly confirmed, independently retained parent test case."""

    __tablename__ = "regression_cases"
    __table_args__ = (
        CheckConstraint(
            "expected_safety_status IN ('passed', 'guardrail', 'blocked')",
            name="ck_regression_cases_safety_status",
        ),
        CheckConstraint(
            "expected_technical_error IN ('none', 'provider_error')",
            name="ck_regression_cases_technical_error",
        ),
        Index("ix_regression_cases_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    source_feedback_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("message_feedback.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("agents.id"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    expected_response: Mapped[str] = mapped_column(Text, nullable=False)
    expected_safety_status: Mapped[str] = mapped_column(String(20), nullable=False)
    expected_safety_rule_id: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )
    expected_technical_error: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="none",
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
        onupdate=func.now(),
    )

    source_feedback: Mapped[MessageFeedback | None] = relationship(
        back_populates="regression_cases"
    )
    agent: Mapped["Agent"] = relationship()
