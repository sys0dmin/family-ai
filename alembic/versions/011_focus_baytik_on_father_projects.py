"""Keep Baytik accurate about the father's office IT project role."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "011_baytik_father_projects"
down_revision: str | None = "010_baytik_father_voice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BAYTIK_V2_ID = "a0000000-0000-4000-8000-00000000000b"
BAYTIK_V3_ID = "a0000000-0000-4000-8000-00000000000c"
FATHER_ROLE_RULES = (
    " Папа работает в ИТ-поддержке офисов X5 Tech и ведёт важные проекты. Когда рассказываешь "
    "о своей работе, сначала объясняй проектную и инженерную часть: я продумываю и улучшаю офисную "
    "ИТ-инфраструктуру, планирую сложные изменения, принимаю решения, согласую работу людей, "
    "предупреждаю неполадки и отвечаю за результат целиком. Заявки, установка программ и ремонт "
    "компьютеров — лишь небольшая часть работы, не своди рассказ к ним. Не приписывай папе "
    "поддержку магазинных серверов, баз данных, безопасности или других систем, если такой факт "
    "не был сообщён. Не придумывай названия и подробности его проектов: предложи Лере попросить "
    "папу рассказать о них."
)


def upgrade() -> None:
    connection = op.get_bind()
    base_prompt = connection.execute(
        sa.text(
            "SELECT system_prompt FROM agent_revisions "
            "WHERE id = CAST(:revision_id AS UUID)"
        ),
        {"revision_id": BAYTIK_V2_ID},
    ).scalar_one()
    connection.execute(
        sa.text(
            "INSERT INTO agent_revisions "
            "(id, agent_id, version, system_prompt, created_by) "
            "VALUES (CAST(:id AS UUID), 'tech_guide', 3, :prompt, 'migration')"
        ),
        {"id": BAYTIK_V3_ID, "prompt": base_prompt + FATHER_ROLE_RULES},
    )
    connection.execute(
        sa.text(
            "UPDATE agents SET active_revision_id = CAST(:revision_id AS UUID) "
            "WHERE id = 'tech_guide'"
        ),
        {"revision_id": BAYTIK_V3_ID},
    )


def downgrade() -> None:
    connection = op.get_bind()
    has_v3_conversations = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM conversations "
            "WHERE agent_revision_id = CAST(:revision_id AS UUID))"
        ),
        {"revision_id": BAYTIK_V3_ID},
    ).scalar_one()
    if has_v3_conversations:
        return
    connection.execute(
        sa.text(
            "UPDATE agents SET active_revision_id = CAST(:revision_id AS UUID) "
            "WHERE id = 'tech_guide'"
        ),
        {"revision_id": BAYTIK_V2_ID},
    )
    connection.execute(
        sa.text("DELETE FROM agent_revisions WHERE id = CAST(:revision_id AS UUID)"),
        {"revision_id": BAYTIK_V3_ID},
    )
