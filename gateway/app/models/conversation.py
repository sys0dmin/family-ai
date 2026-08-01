"""Conversation ORM model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gateway.app.db.base import Base

if TYPE_CHECKING:
    from gateway.app.models.activity_session import ActivitySession
    from gateway.app.models.agent import Agent, AgentRevision
    from gateway.app.models.child_profile import ChildProfile
    from gateway.app.models.message import Message


class Conversation(Base):
    """A single dialogue session for one child profile."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    child_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("child_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("agents.id"),
        nullable=False,
        index=True,
    )
    agent_revision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_revisions.id"),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    child_profile: Mapped["ChildProfile"] = relationship(back_populates="conversations")
    agent: Mapped["Agent"] = relationship(back_populates="conversations")
    agent_revision: Mapped["AgentRevision"] = relationship(
        foreign_keys=[agent_revision_id],
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        order_by="Message.created_at",
    )
    activity_session: Mapped["ActivitySession | None"] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        uselist=False,
    )
