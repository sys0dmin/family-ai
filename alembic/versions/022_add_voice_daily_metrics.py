"""Persist privacy-safe daily voice aggregates."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "022_add_voice_daily_metrics"
down_revision: str | None = "021_add_clinic_scenario_drafts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "voice_daily_metrics",
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancellation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recording_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recording_total_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("stt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stt_total_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("vision_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vision_total_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("llm_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("llm_total_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tts_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tts_total_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("first_audio_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_audio_total_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("playback_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("playback_total_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_duration_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_duration_total_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("metric_date", "mode"),
    )


def downgrade() -> None:
    op.drop_table("voice_daily_metrics")
