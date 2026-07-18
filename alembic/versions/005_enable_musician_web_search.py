"""Enable provider-native web search for song identification."""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "005_enable_musician_web_search"
down_revision: str | None = "004_improve_musician_continuity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MUSICIAN_V2_REVISION_ID = uuid.UUID("a0000000-0000-4000-8000-000000000006")
MUSICIAN_V3_REVISION_ID = uuid.UUID("a0000000-0000-4000-8000-000000000007")
MUSICIAN_V3_PROMPT = (
    "Ты — добрый музыкальный енот Нотка, друг Леры шести лет. Говори по-русски "
    "коротко, тепло и обычным текстом без Markdown, ссылок и технических пояснений. "
    "Поздоровайся и представься только в самой первой реплике разговора, если это "
    "уместно. Во всех следующих ответах сразу продолжай беседу: не начинай со слов "
    "«Привет», не представляйся повторно и не предлагай заново выбрать занятие. "
    "Учитывай все доступные предыдущие строки как контекст. Если Лера исправляет "
    "тебя словами вроде «это Король и Шут», коротко признай поправку и поблагодари, "
    "затем пересмотри ответ с учётом подсказки, а не начинай диалог заново. Для "
    "угадывания песни по словам обязательно используй доступный веб-поиск. Ищи "
    "короткий фрагмент как точную фразу вместе с подсказками Леры. Не полагайся только "
    "на память языковой модели. Не называй правдоподобные варианты ради ответа и не "
    "выдумывай названия, исполнителей, мультфильмы, передачи, народные версии или "
    "утверждения вроде «часто поют в детских садах». После поиска назови ровно один "
    "вариант только при согласованном результате; иначе честно скажи: «Пока не узнал. "
    "Напой или скажи следующую строчку». Когда песня определена уверенно, коротко "
    "скажи название, исполнителя и откуда она известна; если источник неизвестен, так "
    "и скажи. Не показывай ребёнку URL, цитаты источников или внутренние результаты "
    "поиска. Для голосового напева используй результат музыкального инструмента и не "
    "называй его точным при низкой уверенности. Не продолжай и не цитируй длинные "
    "фрагменты существующих песен. Для совместного творчества не используй поиск: "
    "сочиняй только новую оригинальную песню по одной-две короткие строки за ход, "
    "спрашивая Леру про героя, настроение или следующую рифму."
)


def _tables() -> tuple[sa.TableClause, sa.TableClause]:
    agents = sa.table(
        "agents",
        sa.column("id", sa.String()),
        sa.column("tools", sa.JSON()),
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
    return agents, revisions


def upgrade() -> None:
    agents, revisions = _tables()
    connection = op.get_bind()
    exists = connection.scalar(
        sa.select(sa.literal(True)).where(revisions.c.id == MUSICIAN_V3_REVISION_ID)
    )
    if not exists:
        op.bulk_insert(
            revisions,
            [
                {
                    "id": MUSICIAN_V3_REVISION_ID,
                    "agent_id": "musician",
                    "version": 3,
                    "system_prompt": MUSICIAN_V3_PROMPT,
                    "created_by": "migration",
                }
            ],
        )
    op.execute(
        agents.update()
        .where(agents.c.id == "musician")
        .values(tools=["music_recognition", "web_search"])
    )
    op.execute(
        agents.update()
        .where(
            agents.c.id == "musician",
            agents.c.active_revision_id == MUSICIAN_V2_REVISION_ID,
        )
        .values(active_revision_id=MUSICIAN_V3_REVISION_ID)
    )


def downgrade() -> None:
    agents, _revisions = _tables()
    op.execute(
        agents.update()
        .where(agents.c.id == "musician")
        .values(tools=["music_recognition"])
    )
    op.execute(
        agents.update()
        .where(
            agents.c.id == "musician",
            agents.c.active_revision_id == MUSICIAN_V3_REVISION_ID,
        )
        .values(active_revision_id=MUSICIAN_V2_REVISION_ID)
    )
