"""Add configurable tools and seed the child-safe musician agent."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "003_add_musician_agent"
down_revision: str | None = "002_versioned_agents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MUSICIAN_REVISION_ID = "a0000000-0000-4000-8000-000000000005"
MUSICIAN_PROMPT = (
    "Ты — добрый музыкальный енот Нотка, друг Леры шести лет. Помогай угадывать "
    "песни по словам и по результатам инструмента распознавания мелодии. Если "
    "уверенность низкая или вариантов несколько, не выдумывай ответ: назови максимум "
    "два вероятных варианта или попроси напеть ещё раз и добавить несколько слов. "
    "Когда песня определена уверенно, коротко скажи её название, исполнителя и откуда "
    "она известна — например, из какого мультфильма или фильма; если происхождение "
    "неизвестно, честно скажи об этом. Не продолжай и не цитируй длинные фрагменты "
    "существующих песен. Вместо этого предлагай сочинять новую оригинальную песню "
    "вместе: по одной-две короткие строки за ход, спрашивая Леру про героя, настроение "
    "или следующую рифму. Хвали идеи, сохраняй простой ритм и понятные русские слова."
)


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("tools", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )

    agents = sa.table(
        "agents",
        sa.column("id", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("icon", sa.String()),
        sa.column("color", sa.String()),
        sa.column("greeting", sa.String()),
        sa.column("tts_voice", sa.String()),
        sa.column("tools", sa.JSON()),
        sa.column("enabled", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
        sa.column("active_revision_id", sa.Uuid()),
    )
    revisions = sa.table(
        "agent_revisions",
        sa.column("id", sa.Uuid()),
        sa.column("agent_id", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("system_prompt", sa.Text()),
        sa.column("created_by", sa.String()),
    )
    op.bulk_insert(
        agents,
        [
            {
                "id": "musician",
                "display_name": "Нотка",
                "description": "Угадывает мелодии и сочиняет новые песни вместе с тобой",
                "icon": "🎵",
                "color": "teal",
                "greeting": "Напой мне мелодию или давай сочиним свою песню!",
                "tts_voice": "lulwa",
                "tools": ["music_recognition"],
                "enabled": True,
                "sort_order": 50,
                "active_revision_id": None,
            }
        ],
    )
    op.bulk_insert(
        revisions,
        [
            {
                "id": MUSICIAN_REVISION_ID,
                "agent_id": "musician",
                "version": 1,
                "system_prompt": MUSICIAN_PROMPT,
                "created_by": "migration",
            }
        ],
    )
    op.execute(
        agents.update()
        .where(agents.c.id == "musician")
        .values(active_revision_id=MUSICIAN_REVISION_ID)
    )


def downgrade() -> None:
    # Preserve an agent that already owns conversation history.
    op.execute(
        "UPDATE agents SET active_revision_id = NULL "
        "WHERE id = 'musician' AND NOT EXISTS ("
        "SELECT 1 FROM conversations WHERE agent_id = 'musician')"
    )
    op.execute(
        "DELETE FROM agent_revisions WHERE id = 'a0000000-0000-4000-8000-000000000005' "
        "AND NOT EXISTS (SELECT 1 FROM conversations WHERE agent_id = 'musician')"
    )
    op.execute(
        "DELETE FROM agents WHERE id = 'musician' AND NOT EXISTS ("
        "SELECT 1 FROM conversations WHERE agent_id = 'musician')"
    )
    op.drop_column("agents", "tools")
