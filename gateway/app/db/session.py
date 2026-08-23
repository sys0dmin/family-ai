"""Database engine and session factory."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from gateway.app.config import get_settings

_engine = None
_session_factory: sessionmaker[Session] | None = None


def get_engine():
    """Return a lazily created SQLAlchemy engine."""

    global _engine
    if _engine is None:
        settings = get_settings()
        if not settings.database_url.strip():
            raise RuntimeError(
                "FAMILY_AI_DATABASE_URL is required; Gateway uses PostgreSQL "
                "and does not create an implicit local database"
            )
        connect_args = {}
        if settings.database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(settings.database_url, connect_args=connect_args)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return a lazily created session factory."""

    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _session_factory


def get_db_session() -> Generator[Session]:
    """Yield a database session for request-scoped use."""

    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_database_runtime() -> None:
    """Reset cached engine and session factory (used in tests)."""

    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
