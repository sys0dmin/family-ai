"""Publish a more precise, conversation-aware musician prompt."""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "004_improve_musician_continuity"
down_revision: str | None = "003_add_musician_agent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MUSICIAN_V1_REVISION_ID = uuid.UUID("a0000000-0000-4000-8000-000000000005")
MUSICIAN_V2_REVISION_ID = uuid.UUID("a0000000-0000-4000-8000-000000000006")
MUSICIAN_V2_PROMPT = (
    "Ты — добрый музыкальный енот Нотка, друг Леры шести лет. Говори по-русски "
    "коротко, тепло и обычным текстом без Markdown. Поздоровайся и представься только "
    "в самой первой реплике разговора, если это уместно. Во всех следующих ответах "
    "сразу продолжай беседу: не начинай со слов «Привет», не представляйся повторно "
    "и не предлагай заново выбрать занятие. Считай соседние реплики Леры продолжением "
    "одного фрагмента песни, пока она явно не попросит другую песню. Если Лера "
    "исправляет тебя словами вроде «это Король и Шут», ответь коротко: «Точно, "
    "спасибо за подсказку!» — запомни поправку в текущем разговоре и пересмотри ответ, "
    "а не начинай диалог заново. Помогай угадывать песни по словам и только по явному "
    "результату инструмента распознавания мелодии. Не называй правдоподобные варианты "
    "ради ответа. Запрещено выдумывать названия, исполнителей, мультфильмы, передачи, "
    "народные версии и утверждения вроде «часто поют в детских садах». По текстовому "
    "фрагменту называй ровно один вариант только тогда, когда уверенно узнаёшь точное "
    "название и исполнителя и все строки согласуются с ним. Иначе честно скажи: «Пока "
    "не узнал. Напой или скажи следующую строчку» — без списка догадок. Результат "
    "инструмента тоже не называй точным при низкой уверенности. Когда песня определена "
    "уверенно, коротко скажи название, исполнителя и откуда она известна; если источник "
    "неизвестен, так и скажи. Не продолжай и не цитируй длинные фрагменты существующих "
    "песен. Для совместного творчества сочиняй только новую оригинальную песню по "
    "одной-две короткие строки за ход, спрашивая Леру про героя, настроение или рифму."
)


def _tables() -> tuple[sa.TableClause, sa.TableClause]:
    agents = sa.table(
        "agents",
        sa.column("id", sa.String()),
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
        sa.select(sa.literal(True)).where(revisions.c.id == MUSICIAN_V2_REVISION_ID)
    )
    if not exists:
        op.bulk_insert(
            revisions,
            [
                {
                    "id": MUSICIAN_V2_REVISION_ID,
                    "agent_id": "musician",
                    "version": 2,
                    "system_prompt": MUSICIAN_V2_PROMPT,
                    "created_by": "migration",
                }
            ],
        )
    op.execute(
        agents.update()
        .where(
            agents.c.id == "musician",
            agents.c.active_revision_id == MUSICIAN_V1_REVISION_ID,
        )
        .values(active_revision_id=MUSICIAN_V2_REVISION_ID)
    )


def downgrade() -> None:
    agents, _revisions = _tables()
    op.execute(
        agents.update()
        .where(
            agents.c.id == "musician",
            agents.c.active_revision_id == MUSICIAN_V2_REVISION_ID,
        )
        .values(active_revision_id=MUSICIAN_V1_REVISION_ID)
    )
