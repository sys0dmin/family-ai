"""Purge transcript messages older than the retention window."""

from gateway.app.config import get_settings
from gateway.app.db.session import get_session_factory
from gateway.app.services.retention_service import RetentionService


def main() -> None:
    settings = get_settings()
    session = get_session_factory()()
    try:
        deleted = RetentionService(session, settings.message_retention_days).purge_expired_messages()
        session.commit()
        print(f"Deleted {deleted} expired message(s).")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
