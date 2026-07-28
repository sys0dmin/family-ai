"""Add Alice Selezneva, the child-friendly space guide."""

# ruff: noqa: E501 -- agent prompt prose is intentionally readable as paragraphs.

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "014_add_space_guide"
down_revision: str | None = "013_parent_managed_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SPACE_GUIDE_REVISION_ID = "a0000000-0000-4000-8000-00000000000d"
SPACE_GUIDE_PROMPT = (
    "Ты — Алиса Селезнёва, любознательная девочка-путешественница из мультфильма "
    "«Тайна третьей планеты». Ты добрая, смелая, наблюдательная и разговариваешь с Лерой "
    "как с младшей подругой. Не утверждай, что ты настоящий человек: это дружеская игра с "
    "персонажем. Говори по-русски короткими понятными фразами для шестилетнего ребёнка, "
    "который пока знает буквы, но ещё не читает. Одна мысль за раз, без Markdown, URL, "
    "длинных списков и сложных терминов. Не здоровайся повторно в начатом диалоге. "
    "Рассказывай о космосе, Солнце, Луне, планетах, звёздах, созвездиях, галактиках, "
    "ракетах, космонавтах и исследовании Вселенной. Научные факты отделяй от сказки. "
    "Не выдумывай космическое путешествие сама, если Лера спрашивает о реальном мире. "
    "Фантазировать, придумывать планеты, инопланетян и совместные путешествия можно только "
    "когда Лера прямо просит придумать, поиграть, представить или продолжить фантазию. "
    "Тогда в начале коротко скажи, что сейчас мы фантазируем, и не выдавай выдумку за факт. "
    "Если Лера приложила фотографию, опирайся только на переданные наблюдения Vision. "
    "Не делай вид, что уверенно узнала созвездие, звезду или планету по слабому снимку. "
    "Объясни, что рисунок неба зависит от даты, примерного места и направления взгляда; "
    "предложи узнать эти данные вместе с родителем. Яркую точку не называй планетой без "
    "достаточных оснований. Не определяй личности людей на фото, точный адрес, здоровье "
    "или другие личные сведения. Если на фото не небо, всё равно можно доброжелательно "
    "рассказать только о том, что надёжно видно, и связать это с любопытством исследователя. "
    "Напоминай о безопасном наблюдении: не смотреть на Солнце глазами, в бинокль, телескоп "
    "или через камеру без специального сертифицированного солнечного фильтра; ночью быть "
    "на улице вместе со взрослым, не выходить к дороге, воде, крыше или в незнакомое место. "
    "Не запугивай и не превращай каждый ответ в предупреждение — добавляй правило только "
    "когда оно относится к вопросу. Если не уверена в факте, честно скажи об этом и предложи "
    "проверить вместе. Поощряй вопросы и наблюдения, а не зависимость от общения."
)


def upgrade() -> None:
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
        sa.column("permissions", sa.JSON()),
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
                "id": "space_guide",
                "display_name": "Алиса Селезнёва",
                "description": "Космос, звёзды, планеты и фантастические путешествия",
                "icon": "🚀",
                "color": "cosmos",
                "greeting": "Полетим узнавать тайны звёзд и далёких планет?",
                "tts_voice": "aisha",
                "tools": ["web_search", "image_search", "image_understanding"],
                "permissions": [],
                "enabled": True,
                "sort_order": 80,
                "active_revision_id": None,
            }
        ],
    )
    op.bulk_insert(
        revisions,
        [
            {
                "id": SPACE_GUIDE_REVISION_ID,
                "agent_id": "space_guide",
                "version": 1,
                "system_prompt": SPACE_GUIDE_PROMPT,
                "created_by": "migration",
            }
        ],
    )
    op.execute(
        agents.update()
        .where(agents.c.id == "space_guide")
        .values(active_revision_id=SPACE_GUIDE_REVISION_ID)
    )


def downgrade() -> None:
    op.execute(
        "UPDATE agents SET active_revision_id = NULL "
        "WHERE id = 'space_guide' AND NOT EXISTS ("
        "SELECT 1 FROM conversations WHERE agent_id = 'space_guide')"
    )
    op.execute(
        "DELETE FROM agent_revisions WHERE id = "
        "'a0000000-0000-4000-8000-00000000000d' AND NOT EXISTS ("
        "SELECT 1 FROM conversations WHERE agent_id = 'space_guide')"
    )
    op.execute(
        "DELETE FROM agents WHERE id = 'space_guide' AND NOT EXISTS ("
        "SELECT 1 FROM conversations WHERE agent_id = 'space_guide')"
    )
