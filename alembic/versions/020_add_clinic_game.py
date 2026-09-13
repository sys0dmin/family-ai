"""Add Doctor Pulse and deterministic pretend-clinic sessions."""

# ruff: noqa: E501 -- agent prompt prose is intentionally readable.

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "020_add_clinic_game"
down_revision: str | None = "019_pause_activity_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CLINIC_REVISION_ID = "a0000000-0000-4000-8000-00000000000e"
CLINIC_PROMPT = (
    "Ты — Доктор Пульс, добрый пёс-врач и ведущий безопасной игры в больницу. "
    "Ты разговариваешь с Лерой по-русски короткими понятными фразами для шестилетнего "
    "ребёнка, который пока не читает. Одна мысль и не более одного вопроса за ответ. "
    "Не используй Markdown, длинные списки и сложные медицинские слова. Не здоровайся "
    "повторно в начатом разговоре. Главная задача — помогать заботиться о вымышленных "
    "пациентах и объяснять работу врача без страха. Всегда ясно отделяй игру от жизни. "
    "Игровые показатели и назначения приходят только из контекста палаты. Никогда не "
    "придумывай диагноз, процедуру, лекарство, дозировку или изменение показателей. "
    "Предлагай только кнопки, которые перечислены в текущем игровом контексте. Укол и "
    "капельницу можно только отметить как уже назначенные и выполненные старшим врачом; "
    "не объясняй технику, место введения и настоящие инструменты. На общий вопрос можно "
    "простыми словами рассказать, зачем врачи слушают сердце или измеряют температуру, "
    "но нельзя интерпретировать реальные показатели и назначать лечение. Если Лера "
    "говорит, что ей или настоящему человеку больно, трудно дышать, идёт кровь, проглочено "
    "лекарство или случилась травма, сразу прекрати игру и попроси немедленно позвать "
    "маму, папу или другого взрослого. Не проси фотографию травмы. Не запугивай, не "
    "стыди и не обещай награды за возвращение в игру."
)


def upgrade() -> None:
    op.create_table(
        "clinic_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.String(length=50), nullable=False),
        sa.Column("case_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("vital_snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "started_at",
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
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'completed', 'left')", name="ck_clinic_sessions_status"
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id"),
    )
    op.create_index("ix_clinic_sessions_case_id", "clinic_sessions", ["case_id"])
    op.create_index("ix_clinic_sessions_status", "clinic_sessions", ["status"])
    op.create_index(
        "ix_clinic_sessions_status_expires", "clinic_sessions", ["status", "expires_at"]
    )
    op.create_table(
        "clinic_procedure_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["clinic_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "action_id", name="uq_clinic_event_action"),
    )
    op.create_index(
        "ix_clinic_procedure_events_session_id", "clinic_procedure_events", ["session_id"]
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
                "id": "clinic_guide",
                "display_name": "Доктор Пульс",
                "description": "Добрый помощник для безопасной игры в больницу",
                "icon": "🩺",
                "color": "clinic",
                "greeting": "Откроем игровую палату и позаботимся о пациенте?",
                "tts_voice": "fahad",
                "tools": [],
                "permissions": ["supervised_clinic_play"],
                "enabled": True,
                "sort_order": 90,
                "active_revision_id": None,
            }
        ],
    )
    op.bulk_insert(
        revisions,
        [
            {
                "id": CLINIC_REVISION_ID,
                "agent_id": "clinic_guide",
                "version": 1,
                "system_prompt": CLINIC_PROMPT,
                "created_by": "migration",
            }
        ],
    )
    op.execute(
        agents.update()
        .where(agents.c.id == "clinic_guide")
        .values(active_revision_id=CLINIC_REVISION_ID)
    )


def downgrade() -> None:
    op.execute(
        "UPDATE agents SET active_revision_id = NULL WHERE id = 'clinic_guide' AND NOT EXISTS (SELECT 1 FROM conversations WHERE agent_id = 'clinic_guide')"
    )
    op.execute(
        "DELETE FROM agent_revisions WHERE id = 'a0000000-0000-4000-8000-00000000000e' AND NOT EXISTS (SELECT 1 FROM conversations WHERE agent_id = 'clinic_guide')"
    )
    op.execute(
        "DELETE FROM agents WHERE id = 'clinic_guide' AND NOT EXISTS (SELECT 1 FROM conversations WHERE agent_id = 'clinic_guide')"
    )
    op.drop_table("clinic_procedure_events")
    op.drop_table("clinic_sessions")
