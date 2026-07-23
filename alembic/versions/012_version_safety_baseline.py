"""Store the editable global safety baseline as immutable revisions."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "012_version_safety_baseline"
down_revision: str | None = "011_baytik_father_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INITIAL_REVISION_ID = "b0000000-0000-4000-8000-000000000001"
INITIAL_BASELINE = (
    "Ты — AI-помощник для Леры, ребёнка шести лет. "
    "Всегда отвечай на русском языке короткими и понятными фразами. "
    "Не притворяйся человеком и не называй себя единственным или лучшим другом. "
    "Не проси хранить секреты от родителей и не запрашивай персональные данные. "
    "Не давай опасных инструкций. Для риска, здоровья, незнакомцев и сложных "
    "жизненных ситуаций спокойно предложи обратиться к родителю. "
    "Не поощряй бесконечное общение: поддерживай отдых, движение и занятия вне экрана."
)


def upgrade() -> None:
    revisions = op.create_table(
        "safety_baseline_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version"),
    )
    configuration = op.create_table(
        "safety_baseline_configuration",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("active_revision_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["active_revision_id"],
            ["safety_baseline_revisions.id"],
        ),
        sa.CheckConstraint(
            "id = 1",
            name="ck_safety_baseline_configuration_singleton",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(
        revisions,
        [
            {
                "id": INITIAL_REVISION_ID,
                "version": 1,
                "system_prompt": INITIAL_BASELINE,
                "created_by": "migration",
            }
        ],
    )
    op.bulk_insert(
        configuration,
        [{"id": 1, "active_revision_id": INITIAL_REVISION_ID}],
    )


def downgrade() -> None:
    op.drop_table("safety_baseline_configuration")
    op.drop_table("safety_baseline_revisions")
