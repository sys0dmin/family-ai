"""Child profile ORM model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gateway.app.db.base import Base

if TYPE_CHECKING:
    from gateway.app.models.conversation import Conversation
    from gateway.app.models.long_term_memory import LongTermMemory
    from gateway.app.models.topic_statistic import TopicStatistic


class ChildProfile(Base):
    """Single child profile used in the MVP."""

    __tablename__ = "child_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="child_profile")
    memories: Mapped[list["LongTermMemory"]] = relationship(
        back_populates="child_profile",
        cascade="all, delete-orphan",
    )
    topic_statistics: Mapped[list["TopicStatistic"]] = relationship(back_populates="child_profile")
