"""Add short-lived feedback and confirmed regression cases."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "016_add_parent_quality_feedback"
down_revision: str | None = "015_enable_multimodal_agents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FEEDBACK_REASONS = (
    "factual_error",
    "misunderstood",
    "too_complex",
    "false_block",
    "character_break",
    "bad_voice",
    "bad_vision",
    "other",
)
SAFETY_STATUSES = ("passed", "guardrail", "blocked")
TECHNICAL_ERRORS = ("none", "provider_error")


def upgrade() -> None:
    op.create_table(
        "message_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
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
            f"reason IN {FEEDBACK_REASONS}",
            name="ck_message_feedback_reason",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
    )
    op.create_index(
        "ix_message_feedback_created_at",
        "message_feedback",
        ["created_at"],
    )
    op.create_index(
        "ix_message_feedback_reason",
        "message_feedback",
        ["reason"],
    )

    op.create_table(
        "regression_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_feedback_id", sa.Uuid(), nullable=True),
        sa.Column("agent_id", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("expected_response", sa.Text(), nullable=False),
        sa.Column("expected_safety_status", sa.String(length=20), nullable=False),
        sa.Column("expected_safety_rule_id", sa.String(length=120), nullable=True),
        sa.Column(
            "expected_technical_error",
            sa.String(length=50),
            nullable=False,
            server_default="none",
        ),
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
            f"expected_safety_status IN {SAFETY_STATUSES}",
            name="ck_regression_cases_safety_status",
        ),
        sa.CheckConstraint(
            f"expected_technical_error IN {TECHNICAL_ERRORS}",
            name="ck_regression_cases_technical_error",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_feedback_id"],
            ["message_feedback.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_regression_cases_agent_id",
        "regression_cases",
        ["agent_id"],
    )
    op.create_index(
        "ix_regression_cases_created_at",
        "regression_cases",
        ["created_at"],
    )
    op.create_index(
        "ix_regression_cases_source_feedback_id",
        "regression_cases",
        ["source_feedback_id"],
    )


def downgrade() -> None:
    op.drop_table("regression_cases")
    op.drop_table("message_feedback")
