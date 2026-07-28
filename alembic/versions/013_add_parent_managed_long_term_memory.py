"""Add structured, parent-confirmed long-term memory."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "013_parent_managed_memory"
down_revision: str | None = "012_version_safety_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "long_term_memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("child_profile_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("topic", sa.String(length=120), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_note", sa.String(length=500), nullable=True),
        sa.Column("source_date", sa.Date(), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("updated_by", sa.String(length=100), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
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
        sa.CheckConstraint(
            "category IN ('interest', 'preference', 'learning_progress')",
            name="ck_long_term_memories_category",
        ),
        sa.CheckConstraint(
            "source_type IN "
            "('parent_observation', 'child_statement', 'learning_activity')",
            name="ck_long_term_memories_source_type",
        ),
        sa.ForeignKeyConstraint(
            ["child_profile_id"],
            ["child_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_long_term_memories_child_profile_id",
        "long_term_memories",
        ["child_profile_id"],
    )
    op.create_index(
        "ix_long_term_memories_profile_category_updated",
        "long_term_memories",
        ["child_profile_id", "category", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_long_term_memories_profile_category_updated",
        table_name="long_term_memories",
    )
    op.drop_index(
        "ix_long_term_memories_child_profile_id",
        table_name="long_term_memories",
    )
    op.drop_table("long_term_memories")
