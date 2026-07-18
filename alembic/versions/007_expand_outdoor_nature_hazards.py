"""Expand the outdoor guide to educational wilderness hazards."""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "007_expand_nature_hazards"
down_revision: str | None = "006_add_outdoor_guide_agent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OUTDOOR_V1_REVISION_ID = uuid.UUID("a0000000-0000-4000-8000-000000000008")
OUTDOOR_V2_REVISION_ID = uuid.UUID("a0000000-0000-4000-8000-000000000009")
NATURE_HAZARDS_ADDENDUM = (
    " Свободно и спокойно рассказывай об опасностях дикой природы: ядовитых "
    "растениях, грибах и ягодах, клещах, насекомых, змеях, диких животных, "
    "воде, погоде, обрывах и других походных рисках. Можно называть известные "
    "примеры и просто объяснять, чем они опасны. Например, волчью ягоду нельзя есть, "
    "а сильный запах багульника может вызвать головную боль. Для точных фактов "
    "используй доступный веб-поиск, но не показывай ребёнку ссылки и технические "
    "детали поиска. Не запугивай и не давай графических подробностей. Всегда давай "
    "понятное безопасное действие: не трогать, не пробовать, не подходить, спокойно "
    "отойти и сразу рассказать родителям. Никогда не определяй найденный вид по только "
    "по описанию или фотографии и не учи получать или использовать яд."
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
    prompt_v1 = connection.scalar(
        sa.select(revisions.c.system_prompt).where(revisions.c.id == OUTDOOR_V1_REVISION_ID)
    )
    if prompt_v1 is None:
        raise RuntimeError("Outdoor guide v1 revision is missing")

    exists = connection.scalar(
        sa.select(sa.literal(True)).where(revisions.c.id == OUTDOOR_V2_REVISION_ID)
    )
    if not exists:
        op.bulk_insert(
            revisions,
            [
                {
                    "id": OUTDOOR_V2_REVISION_ID,
                    "agent_id": "outdoor_guide",
                    "version": 2,
                    "system_prompt": prompt_v1 + NATURE_HAZARDS_ADDENDUM,
                    "created_by": "migration",
                }
            ],
        )

    op.execute(
        agents.update().where(agents.c.id == "outdoor_guide").values(tools=["web_search"])
    )
    op.execute(
        agents.update()
        .where(
            agents.c.id == "outdoor_guide",
            agents.c.active_revision_id == OUTDOOR_V1_REVISION_ID,
        )
        .values(active_revision_id=OUTDOOR_V2_REVISION_ID)
    )


def downgrade() -> None:
    agents, _revisions = _tables()
    op.execute(agents.update().where(agents.c.id == "outdoor_guide").values(tools=[]))
    op.execute(
        agents.update()
        .where(
            agents.c.id == "outdoor_guide",
            agents.c.active_revision_id == OUTDOOR_V2_REVISION_ID,
        )
        .values(active_revision_id=OUTDOOR_V1_REVISION_ID)
    )
