"""Message ORM model."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gateway.app.db.base import Base

if TYPE_CHECKING:
    from gateway.app.models.conversation import Conversation
    from gateway.app.models.message_media import MessageMedia


class MessageRole(StrEnum):
    """Author of a stored transcript line."""

    CHILD = "child"
    ASSISTANT = "assistant"


class Message(Base):
    """A single child or assistant transcript line."""

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),
        Index("ix_messages_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    media: Mapped[list["MessageMedia"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
