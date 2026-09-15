"""Parent-authored, versioned overlays for pretend-clinic scenarios."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from gateway.app.db.base import Base


class ClinicScenarioDraft(Base):
    __tablename__ = "clinic_scenario_drafts"
    __table_args__ = (UniqueConstraint("case_id", "version", name="uq_clinic_draft_version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    payload: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False, default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
