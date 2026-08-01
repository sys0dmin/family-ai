"""Add short-lived configured activity state."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "017_add_activity_sessions"
down_revision: str | None = "016_add_parent_quality_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "activity_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("activity_id", sa.String(length=50), nullable=False),
        sa.Column("activity_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_step", sa.Integer(), nullable=False),
        sa.Column("completion_summary", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'cancelled', 'left')",
            name="ck_activity_sessions_status",
        ),
        sa.CheckConstraint("current_step >= 0", name="ck_activity_sessions_step"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id"),
    )
    op.create_index("ix_activity_sessions_activity_id", "activity_sessions", ["activity_id"])
    op.create_index("ix_activity_sessions_status", "activity_sessions", ["status"])
    op.create_index(
        "ix_activity_sessions_status_expires",
        "activity_sessions",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_table("activity_sessions")
