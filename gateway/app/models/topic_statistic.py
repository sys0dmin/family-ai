"""Topic statistic ORM model."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gateway.app.db.base import Base

if TYPE_CHECKING:
    from gateway.app.models.child_profile import ChildProfile


class TopicStatistic(Base):
    """Aggregated topic activity without message text."""

    __tablename__ = "topic_statistics"
    __table_args__ = (
        UniqueConstraint(
            "child_profile_id",
            "topic",
            "stat_date",
            name="uq_topic_statistics_profile_topic_date",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    child_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("child_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    stat_date: Mapped[date] = mapped_column(Date, nullable=False)
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

    child_profile: Mapped["ChildProfile"] = relationship(back_populates="topic_statistics")
