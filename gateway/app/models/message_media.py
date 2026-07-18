"""Media attachment linked to a conversation message."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gateway.app.db.base import Base

if TYPE_CHECKING:
    from gateway.app.models.message import Message


class MessageMedia(Base):
    """Licensed media metadata; binary content remains at its source."""

    __tablename__ = "message_media"
    __table_args__ = (Index("ix_message_media_message_id", "message_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    remote_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    creator: Mapped[str | None] = mapped_column(String(200))
    license_name: Mapped[str] = mapped_column(String(50), nullable=False)
    license_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    message: Mapped["Message"] = relationship(back_populates="media")

    @property
    def content_url(self) -> str:
        return f"/v1/media/{self.id}/content"

    @property
    def attribution(self) -> str:
        parts = [part for part in (self.creator, self.license_name) if part]
        return " · ".join(parts)

