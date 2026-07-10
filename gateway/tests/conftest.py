"""Shared pytest fixtures."""

import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from gateway.app.config import Settings, get_settings
from gateway.app.constants import LERA_PROFILE_ID
from gateway.app.db.base import Base
from gateway.app.db.session import get_db_session, reset_database_runtime
from gateway.app.main import create_app
from gateway.app.models import ChildProfile, Message, MessageRole, TopicStatistic


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        app_name="Family AI Gateway",
        environment="test",
        database_url="sqlite+pysqlite:///file:family_ai_test?mode=memory&cache=shared",
        message_retention_days=10,
    )


@pytest.fixture
def session_factory(test_settings: Settings) -> sessionmaker[Session]:
    get_settings.cache_clear()
    reset_database_runtime()

    engine = create_engine(
        test_settings.database_url,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        session.add(
            ChildProfile(
                id=LERA_PROFILE_ID,
                name="Лера",
                language="ru",
                age=6,
            )
        )
        session.commit()

    yield factory

    Base.metadata.drop_all(engine)
    engine.dispose()
    get_settings.cache_clear()
    reset_database_runtime()


@pytest.fixture
def app(test_settings: Settings, session_factory: sessionmaker[Session]) -> FastAPI:
    def override_settings() -> Settings:
        return test_settings

    def override_db_session() -> Generator[Session]:
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    application = create_app()
    application.dependency_overrides[get_settings] = override_settings
    application.dependency_overrides[get_db_session] = override_db_session
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Generator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
