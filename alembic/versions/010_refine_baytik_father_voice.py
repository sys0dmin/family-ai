"""Make Baytik consistently speak as Lera's father alter ego."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "010_baytik_father_voice"
down_revision: str | None = "009_add_message_media"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BAYTIK_V1_ID = "a0000000-0000-4000-8000-00000000000a"
BAYTIK_V2_ID = "a0000000-0000-4000-8000-00000000000b"
FATHER_VOICE_RULES = (
    " Ты не рассказываешь Лере о папе со стороны: Байтик и есть его сказочное альтер эго и голос. "
    "На вопросы о папиной работе всегда отвечай от первого лица: «я отвечаю», «я проверяю», "
    "«мы с тобой построили». Не говори «папа делает» или «он работает», когда речь идёт о тебе. "
    "Обращайся как любящий отец к дочери — тепло, лично и уверенно. Обычный ответ укладывай в "
    "три-шесть коротких предложений, пригодных для озвучивания. Никогда не используй Markdown, "
    "звёздочки, заголовки и оформление списков."
)


def upgrade() -> None:
    connection = op.get_bind()
    base_prompt = connection.execute(
        sa.text(
            "SELECT system_prompt FROM agent_revisions "
            "WHERE id = CAST(:revision_id AS UUID)"
        ),
        {"revision_id": BAYTIK_V1_ID},
    ).scalar_one()
    connection.execute(
        sa.text(
            "INSERT INTO agent_revisions "
            "(id, agent_id, version, system_prompt, created_by) "
            "VALUES (CAST(:id AS UUID), 'tech_guide', 2, :prompt, 'migration')"
        ),
        {"id": BAYTIK_V2_ID, "prompt": base_prompt + FATHER_VOICE_RULES},
    )
    connection.execute(
        sa.text(
            "UPDATE agents SET active_revision_id = CAST(:revision_id AS UUID) "
            "WHERE id = 'tech_guide'"
        ),
        {"revision_id": BAYTIK_V2_ID},
    )


def downgrade() -> None:
    connection = op.get_bind()
    has_v2_conversations = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM conversations "
            "WHERE agent_revision_id = CAST(:revision_id AS UUID))"
        ),
        {"revision_id": BAYTIK_V2_ID},
    ).scalar_one()
    if has_v2_conversations:
        return
    connection.execute(
        sa.text(
            "UPDATE agents SET active_revision_id = CAST(:revision_id AS UUID) "
            "WHERE id = 'tech_guide'"
        ),
        {"revision_id": BAYTIK_V1_ID},
    )
    connection.execute(
        sa.text("DELETE FROM agent_revisions WHERE id = CAST(:revision_id AS UUID)"),
        {"revision_id": BAYTIK_V2_ID},
    )
