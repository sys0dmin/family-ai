"""Versioned AI agent configuration models."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gateway.app.db.base import Base

if TYPE_CHECKING:
    from gateway.app.models.conversation import Conversation


class Agent(Base):
    """Child-visible agent metadata and its currently published revision."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    icon: Mapped[str] = mapped_column(String(20), nullable=False)
    color: Mapped[str] = mapped_column(String(20), nullable=False)
    greeting: Mapped[str] = mapped_column(String(300), nullable=False)
    tts_voice: Mapped[str | None] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "agent_revisions.id",
            name="fk_agents_active_revision_id",
            use_alter=True,
        ),
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

    revisions: Mapped[list["AgentRevision"]] = relationship(
        back_populates="agent",
        foreign_keys="AgentRevision.agent_id",
        cascade="all, delete-orphan",
    )
    active_revision: Mapped["AgentRevision | None"] = relationship(
        foreign_keys=[active_revision_id],
        post_update=True,
    )
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="agent")


class AgentRevision(Base):
    """Immutable version of an agent personality prompt."""

    __tablename__ = "agent_revisions"
    __table_args__ = (
        UniqueConstraint("agent_id", "version", name="uq_agent_revisions_agent_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    agent: Mapped[Agent] = relationship(
        back_populates="revisions",
        foreign_keys=[agent_id],
    )
