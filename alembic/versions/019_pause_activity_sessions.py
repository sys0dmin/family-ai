"""Allow configured activities to be paused and resumed."""

from collections.abc import Sequence

from alembic import op

revision: str = "019_pause_activity_sessions"
down_revision: str | None = "018_add_operational_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_activity_sessions_status",
        "activity_sessions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_activity_sessions_status",
        "activity_sessions",
        "status IN ('active', 'paused', 'completed', 'cancelled', 'left')",
    )
    # Before pause existed, an explicit stop was stored as cancelled. Preserve
    # still-retained sessions so the first upgraded client can continue them.
    op.execute(
        "UPDATE activity_sessions SET status = 'paused' "
        "WHERE status = 'cancelled' AND expires_at > CURRENT_TIMESTAMP"
    )


def downgrade() -> None:
    op.execute("UPDATE activity_sessions SET status = 'cancelled' WHERE status = 'paused'")
    op.drop_constraint(
        "ck_activity_sessions_status",
        "activity_sessions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_activity_sessions_status",
        "activity_sessions",
        "status IN ('active', 'completed', 'cancelled', 'left')",
    )
