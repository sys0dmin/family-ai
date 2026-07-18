"""Add licensed visual attachments to conversation messages."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "009_add_message_media"
down_revision: str | None = "008_add_tech_guide"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "message_media",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("remote_url", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("creator", sa.String(length=200), nullable=True),
        sa.Column("license_name", sa.String(length=50), nullable=False),
        sa.Column("license_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_message_media_message_id", "message_media", ["message_id"])

    agents = sa.table(
        "agents",
        sa.column("id", sa.String()),
        sa.column("tools", sa.JSON()),
    )
    tool_sets = {
        "teacher_friend": ["image_search"],
        "scientist": ["image_search"],
        "outdoor_guide": ["web_search", "image_search"],
        "tech_guide": ["web_search", "image_search"],
    }
    for agent_id, tools in tool_sets.items():
        op.execute(agents.update().where(agents.c.id == agent_id).values(tools=tools))


def downgrade() -> None:
    agents = sa.table(
        "agents",
        sa.column("id", sa.String()),
        sa.column("tools", sa.JSON()),
    )
    tool_sets = {
        "teacher_friend": [],
        "scientist": [],
        "outdoor_guide": ["web_search"],
        "tech_guide": ["web_search"],
    }
    for agent_id, tools in tool_sets.items():
        op.execute(agents.update().where(agents.c.id == agent_id).values(tools=tools))
    op.drop_index("ix_message_media_message_id", table_name="message_media")
    op.drop_table("message_media")
