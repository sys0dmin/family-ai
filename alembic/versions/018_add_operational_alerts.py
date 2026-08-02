"""Add privacy-safe local operational alert episodes."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "018_add_operational_alerts"
down_revision: str | None = "017_add_activity_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operational_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=160), nullable=False),
        sa.Column("scope", sa.String(length=40), nullable=False),
        sa.Column("metric", sa.String(length=60), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=False),
        sa.Column("current_value", sa.Float(), nullable=True),
        sa.Column("threshold_value", sa.Float(), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=120), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "severity IN ('warning', 'critical')",
            name="ck_operational_alerts_severity",
        ),
        sa.CheckConstraint("occurrence_count >= 1", name="ck_operational_alerts_occurrences"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operational_alerts_fingerprint", "operational_alerts", ["fingerprint"])
    op.create_index(
        "ix_operational_alerts_fingerprint_active",
        "operational_alerts",
        ["fingerprint", "resolved_at"],
    )
    op.create_index(
        "ix_operational_alerts_history",
        "operational_alerts",
        ["last_seen_at", "resolved_at"],
    )


def downgrade() -> None:
    op.drop_table("operational_alerts")
