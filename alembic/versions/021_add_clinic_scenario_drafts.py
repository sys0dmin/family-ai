"""Store versioned parent-authored clinic scenario overlays."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "021_add_clinic_scenario_drafts"
down_revision: str | None = "020_add_clinic_game"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clinic_scenario_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.String(length=50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('draft', 'published', 'superseded')", name="ck_clinic_draft_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "version", name="uq_clinic_draft_version"),
    )
    op.create_index("ix_clinic_scenario_drafts_case_id", "clinic_scenario_drafts", ["case_id"])
    op.create_index("ix_clinic_scenario_drafts_status", "clinic_scenario_drafts", ["status"])


def downgrade() -> None:
    op.drop_table("clinic_scenario_drafts")
