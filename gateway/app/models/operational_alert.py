"""Persistent episodes for local, privacy-safe operational alerts."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, Index, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from gateway.app.db.base import Base


class OperationalAlert(Base):
    """One technical degradation episode detected inside Family AI."""

    __tablename__ = "operational_alerts"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('warning', 'critical')",
            name="ck_operational_alerts_severity",
        ),
        CheckConstraint("occurrence_count >= 1", name="ck_operational_alerts_occurrences"),
        Index(
            "ix_operational_alerts_fingerprint_active",
            "fingerprint",
            "resolved_at",
        ),
        Index(
            "ix_operational_alerts_history",
            "last_seen_at",
            "resolved_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(40), nullable=False)
    metric: Mapped[str] = mapped_column(String(60), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    detail: Mapped[str] = mapped_column(String(500), nullable=False)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
