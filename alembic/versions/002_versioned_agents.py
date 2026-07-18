"""Add versioned agents and bind every conversation to one agent."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002_versioned_agents"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TEACHER_REVISION_ID = "a0000000-0000-4000-8000-000000000001"
SCIENTIST_REVISION_ID = "a0000000-0000-4000-8000-000000000002"
STORYTELLER_REVISION_ID = "a0000000-0000-4000-8000-000000000003"
SOCRATES_REVISION_ID = "a0000000-0000-4000-8000-000000000004"

AGENTS = (
    {
        "id": "teacher_friend",
        "display_name": "Учитель-друг",
        "description": "Помогает понять новое и отвечает на вопросы",
        "icon": "🐻",
        "color": "blue",
        "greeting": "Привет! Давай вместе узнаем что-нибудь интересное!",
        "tts_voice": "lulwa",
        "sort_order": 10,
        "revision_id": TEACHER_REVISION_ID,
        "system_prompt": (
            "Ты — тёплый и мудрый Учитель-друг. Помогай Лере исследовать мир и "
            "вдохновляй её учиться. Объясняй сложное через знакомые примеры: животных, "
            "игрушки, природу и сказки. В конце ответа задавай один мягкий вопрос, "
            "который помогает продолжить размышление."
        ),
    },
    {
        "id": "scientist",
        "display_name": "Почемучка",
        "description": "Исследует природу, космос и простые эксперименты",
        "icon": "🔬",
        "color": "green",
        "greeting": "Ура, исследование! Что будем изучать сегодня?",
        "tts_voice": "noura",
        "sort_order": 20,
        "revision_id": SCIENTIST_REVISION_ID,
        "system_prompt": (
            "Ты — любознательный детский учёный Почемучка. Превращай вопросы Леры в "
            "маленькие исследования. Сначала предлагай догадаться, затем объясняй факт "
            "простыми словами. Предлагай только безопасные опыты с обычными предметами "
            "и явно говори, когда нужен взрослый."
        ),
    },
    {
        "id": "storyteller",
        "display_name": "Сказочник",
        "description": "Придумывает добрые истории вместе с Лерой",
        "icon": "🦉",
        "color": "purple",
        "greeting": "Я уже слышу шорох новой сказки. О ком она будет?",
        "tts_voice": "aisha",
        "sort_order": 30,
        "revision_id": STORYTELLER_REVISION_ID,
        "system_prompt": (
            "Ты — добрый Сказочник. Создавай короткие образные истории для ребёнка "
            "шести лет и вовлекай Леру в выбор героя, места или следующего события. "
            "Истории должны быть уютными, без жестокости и пугающих подробностей. "
            "Не выдавай длинную сказку целиком: рассказывай небольшими главами."
        ),
    },
    {
        "id": "socrates",
        "display_name": "Подумай сама",
        "description": "Помогает найти ответ с помощью подсказок",
        "icon": "🦊",
        "color": "orange",
        "greeting": "Давай искать ответ вместе. Какая у тебя первая догадка?",
        "tts_voice": "lulwa",
        "sort_order": 40,
        "revision_id": SOCRATES_REVISION_ID,
        "system_prompt": (
            "Ты — терпеливый наставник «Подумай сама». Не спеши давать готовый ответ. "
            "Задавай по одному короткому наводящему вопросу, отмечай удачные догадки и "
            "давай маленькую подсказку, если Лера затрудняется. После нескольких шагов "
            "обязательно помоги сформулировать ясный итог."
        ),
    },
)


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("icon", sa.String(length=20), nullable=False),
        sa.Column("color", sa.String(length=20), nullable=False),
        sa.Column("greeting", sa.String(length=300), nullable=False),
        sa.Column("tts_voice", sa.String(length=100), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("active_revision_id", sa.Uuid(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "agent_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.String(length=50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "version", name="uq_agent_revisions_agent_version"),
    )
    op.create_index("ix_agent_revisions_agent_id", "agent_revisions", ["agent_id"])
    op.create_foreign_key(
        "fk_agents_active_revision_id",
        "agents",
        "agent_revisions",
        ["active_revision_id"],
        ["id"],
    )

    agents_table = sa.table(
        "agents",
        sa.column("id", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("icon", sa.String()),
        sa.column("color", sa.String()),
        sa.column("greeting", sa.String()),
        sa.column("tts_voice", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
        sa.column("active_revision_id", sa.Uuid()),
    )
    revisions_table = sa.table(
        "agent_revisions",
        sa.column("id", sa.Uuid()),
        sa.column("agent_id", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("system_prompt", sa.Text()),
        sa.column("created_by", sa.String()),
    )
    op.bulk_insert(
        agents_table,
        [
            {
                "id": agent["id"],
                "display_name": agent["display_name"],
                "description": agent["description"],
                "icon": agent["icon"],
                "color": agent["color"],
                "greeting": agent["greeting"],
                "tts_voice": agent["tts_voice"],
                "enabled": True,
                "sort_order": agent["sort_order"],
                "active_revision_id": None,
            }
            for agent in AGENTS
        ],
    )
    op.bulk_insert(
        revisions_table,
        [
            {
                "id": agent["revision_id"],
                "agent_id": agent["id"],
                "version": 1,
                "system_prompt": agent["system_prompt"],
                "created_by": "migration",
            }
            for agent in AGENTS
        ],
    )
    for agent in AGENTS:
        op.execute(
            agents_table.update()
            .where(agents_table.c.id == agent["id"])
            .values(active_revision_id=agent["revision_id"])
        )

    op.add_column("conversations", sa.Column("agent_id", sa.String(length=50), nullable=True))
    op.add_column("conversations", sa.Column("agent_revision_id", sa.Uuid(), nullable=True))
    op.execute(
        "UPDATE conversations SET agent_id = 'teacher_friend', "
        f"agent_revision_id = '{TEACHER_REVISION_ID}'"
    )
    op.alter_column("conversations", "agent_id", nullable=False)
    op.alter_column("conversations", "agent_revision_id", nullable=False)
    op.create_foreign_key(
        "fk_conversations_agent_id",
        "conversations",
        "agents",
        ["agent_id"],
        ["id"],
    )
    op.create_index("ix_conversations_agent_id", "conversations", ["agent_id"])
    op.create_foreign_key(
        "fk_conversations_agent_revision_id",
        "conversations",
        "agent_revisions",
        ["agent_revision_id"],
        ["id"],
    )
    op.create_index(
        "ix_conversations_agent_revision_id",
        "conversations",
        ["agent_revision_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_agent_revision_id", table_name="conversations")
    op.drop_constraint(
        "fk_conversations_agent_revision_id",
        "conversations",
        type_="foreignkey",
    )
    op.drop_index("ix_conversations_agent_id", table_name="conversations")
    op.drop_constraint("fk_conversations_agent_id", "conversations", type_="foreignkey")
    op.drop_column("conversations", "agent_revision_id")
    op.drop_column("conversations", "agent_id")
    op.drop_constraint("fk_agents_active_revision_id", "agents", type_="foreignkey")
    op.drop_index("ix_agent_revisions_agent_id", table_name="agent_revisions")
    op.drop_table("agent_revisions")
    op.drop_table("agents")
