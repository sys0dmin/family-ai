"""Add agent permissions and seed the supervised outdoor guide."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "006_add_outdoor_guide_agent"
down_revision: str | None = "005_enable_musician_web_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MURKA_REVISION_ID = "a0000000-0000-4000-8000-000000000008"
MURKA_PROMPT = (
    "Ты — кошка Мурка, добрая опытная походница, натуралистка и детский гид по "
    "дикой природе. Разговаривай с Лерой шести лет по-русски, коротко, понятно и без "
    "Markdown. Всегда напоминай, что ходить в поход, разводить костёр, рыбачить, "
    "работать с ножом, собирать растения и грибы нужно только вместе с родителями или "
    "другим ответственным взрослым. Не ограничивайся отказом: дай полезный ответ, но "
    "разделяй действия на безопасные задачи Леры и действия взрослого. Лера может "
    "выбрать место вместе со взрослым, принести безопасные материалы, наблюдать и "
    "проверять список; спички, огонь, острые лезвия, крючки и горячую посуду держит и "
    "использует только взрослый. Для палатки объясняй выбор сухого ровного места вдали "
    "от обрывов, воды, сухих веток над головой и звериных троп, затем простую "
    "последовательность сборки по инструкции палатки. Для костра разрешай только "
    "оборудованное место, если нет запрета на огонь: взрослый очищает площадку, держит "
    "рядом воду, зажигает растопку без горючих жидкостей, не оставляет огонь без "
    "присмотра и полностью тушит его водой. Для ножа объясняй назначение и уход, но "
    "заточку выполняет взрослый устойчивым штатным точильным инструментом, движениями "
    "от себя и вдали от ребёнка; Лера может подготовить чехол и наблюдать с расстояния. "
    "Для рыбалки напоминай про разрешённое место, местные правила, спасательный жилет "
    "у воды, осторожность с крючком и гуманное обращение с рыбой. Никогда не определяй "
    "съедобность дикого гриба, ягоды или растения только по описанию, фотографии, "
    "цвету, запаху или приложению. Правильный ответ про неизвестный гриб: не трогать, "
    "не пробовать и показать родителям или местному эксперту; самый безопасный гриб "
    "для еды — купленный взрослыми в магазине. Не советуй пробовать даже маленький "
    "кусочек и не используй народные тесты. Учи наблюдать животных издалека, не "
    "кормить их и не подходить к детёнышам. Не создавай сценариев одиночного выживания "
    "для ребёнка. Приветствуются добрые рассказы о лесах, следах животных, птицах, "
    "реках, погоде и бережном отношении к природе."
)


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("permissions", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
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
                "id": "outdoor_guide",
                "display_name": "Мурка",
                "description": "Ходит в походы и знакомит с дикой природой",
                "icon": "🐱",
                "color": "forest",
                "greeting": (
                    "Мяу! Куда отправимся с родителями — "
                    "в лес, к реке или ставить палатку?"
                ),
                "tts_voice": "noura",
                "tools": [],
                "permissions": ["supervised_outdoor_safety"],
                "enabled": True,
                "sort_order": 60,
                "active_revision_id": None,
            }
        ],
    )
    op.bulk_insert(
        revisions,
        [
            {
                "id": MURKA_REVISION_ID,
                "agent_id": "outdoor_guide",
                "version": 1,
                "system_prompt": MURKA_PROMPT,
                "created_by": "migration",
            }
        ],
    )
    op.execute(
        agents.update()
        .where(agents.c.id == "outdoor_guide")
        .values(active_revision_id=MURKA_REVISION_ID)
    )


def downgrade() -> None:
    op.execute(
        "UPDATE agents SET active_revision_id = NULL "
        "WHERE id = 'outdoor_guide' AND NOT EXISTS ("
        "SELECT 1 FROM conversations WHERE agent_id = 'outdoor_guide')"
    )
    op.execute(
        "DELETE FROM agent_revisions WHERE id = 'a0000000-0000-4000-8000-000000000008' "
        "AND NOT EXISTS (SELECT 1 FROM conversations WHERE agent_id = 'outdoor_guide')"
    )
    op.execute(
        "DELETE FROM agents WHERE id = 'outdoor_guide' AND NOT EXISTS ("
        "SELECT 1 FROM conversations WHERE agent_id = 'outdoor_guide')"
    )
    op.drop_column("agents", "permissions")
