"""Initial schema and Lera profile seed."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LERA_PROFILE_ID = "6f3f8f2a-9c4d-4f1e-b8a2-7d1c5e9a0b12"


def upgrade() -> None:
    message_role = sa.Enum("child", "assistant", name="message_role")

    op.create_table(
        "child_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("child_profile_id", sa.Uuid(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["child_profile_id"], ["child_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_child_profile_id", "conversations", ["child_profile_id"])
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", message_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_messages_conversation_id_created_at",
        "messages",
        ["conversation_id", "created_at"],
    )
    op.create_index("ix_messages_created_at", "messages", ["created_at"])
    op.create_table(
        "topic_statistics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("child_profile_id", sa.Uuid(), nullable=False),
        sa.Column("topic", sa.String(length=100), nullable=False),
        sa.Column("mention_count", sa.Integer(), nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
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
        sa.ForeignKeyConstraint(["child_profile_id"], ["child_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "child_profile_id",
            "topic",
            "stat_date",
            name="uq_topic_statistics_profile_topic_date",
        ),
    )
    op.create_index(
        "ix_topic_statistics_child_profile_id",
        "topic_statistics",
        ["child_profile_id"],
    )

    op.execute(
        sa.text(
            """
            INSERT INTO child_profiles (id, name, language, age)
            VALUES (CAST(:id AS UUID), 'Лера', 'ru', 6)
            """
        ).bindparams(id=LERA_PROFILE_ID)
    )

def downgrade() -> None:
    op.drop_index("ix_topic_statistics_child_profile_id", table_name="topic_statistics")
    op.drop_table("topic_statistics")
    op.drop_index("ix_messages_created_at", table_name="messages")
    op.drop_index("ix_messages_conversation_id_created_at", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversations_child_profile_id", table_name="conversations")
    op.drop_table("conversations")
    op.drop_table("child_profiles")
    sa.Enum(name="message_role").drop(op.get_bind(), checkfirst=True)
