"""Enable ephemeral image understanding for selected existing agents."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "015_enable_multimodal_agents"
down_revision: str | None = "014_add_space_guide"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TARGET_AGENT_IDS = ("teacher_friend", "outdoor_guide", "tech_guide")
TOOL_NAME = "image_understanding"


def _agents_table() -> sa.TableClause:
    return sa.table(
        "agents",
        sa.column("id", sa.String()),
        sa.column("tools", sa.JSON()),
    )


def upgrade() -> None:
    agents = _agents_table()
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(agents.c.id, agents.c.tools).where(
            agents.c.id.in_(TARGET_AGENT_IDS)
        )
    ).mappings()
    for row in rows:
        tools = list(row["tools"] or [])
        if TOOL_NAME not in tools:
            tools.append(TOOL_NAME)
            connection.execute(
                agents.update()
                .where(agents.c.id == row["id"])
                .values(tools=tools)
            )


def downgrade() -> None:
    agents = _agents_table()
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(agents.c.id, agents.c.tools).where(
            agents.c.id.in_(TARGET_AGENT_IDS)
        )
    ).mappings()
    for row in rows:
        tools = [tool for tool in list(row["tools"] or []) if tool != TOOL_NAME]
        connection.execute(
            agents.update()
            .where(agents.c.id == row["id"])
            .values(tools=tools)
        )
