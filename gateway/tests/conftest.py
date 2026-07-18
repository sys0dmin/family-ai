"""Shared pytest fixtures."""

import uuid
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from gateway.app.config import Settings, get_settings
from gateway.app.constants import LERA_PROFILE_ID
from gateway.app.db.base import Base
from gateway.app.db.session import get_db_session, reset_database_runtime
from gateway.app.main import create_app
from gateway.app.models import Agent, AgentRevision, ChildProfile

TEST_AGENTS = (
    ("teacher_friend", "Учитель-друг", "🐻", "blue", "lulwa", 10, ["image_search"], []),
    ("scientist", "Почемучка", "🔬", "green", "noura", 20, ["image_search"], []),
    ("storyteller", "Сказочник", "🦉", "purple", "aisha", 30, [], []),
    ("socrates", "Подумай сама", "🦊", "orange", "lulwa", 40, [], []),
    (
        "musician",
        "Нотка",
        "🎵",
        "teal",
        "lulwa",
        50,
        ["music_recognition", "web_search"],
        [],
    ),
    (
        "outdoor_guide",
        "Мурка",
        "🐱",
        "forest",
        "noura",
        60,
        ["web_search", "image_search"],
        ["supervised_outdoor_safety"],
    ),
    (
        "tech_guide",
        "Байтик",
        "🦝",
        "navy",
        "fahad",
        70,
        ["web_search", "image_search"],
        [],
    ),
)


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
        for agent_id, name, icon, color, voice, sort_order, tools, permissions in TEST_AGENTS:
            session.add(
                Agent(
                    id=agent_id,
                    display_name=name,
                    description=f"Тестовый агент: {name}",
                    icon=icon,
                    color=color,
                    greeting=f"Привет! Я {name}.",
                    tts_voice=voice,
                    enabled=True,
                    sort_order=sort_order,
                    tools=tools,
                    permissions=permissions,
                )
            )
        session.flush()

        for index, (agent_id, name, *_metadata) in enumerate(TEST_AGENTS, start=1):
            session.add(
                AgentRevision(
                    id=uuid.UUID(f"a0000000-0000-0000-0000-{index:012d}"),
                    agent_id=agent_id,
                    version=1,
                    system_prompt=f"Следуй безопасной роли агента {name}.",
                    created_by="test",
                )
            )
        session.flush()

        for index, (agent_id, *_metadata) in enumerate(TEST_AGENTS, start=1):
            agent = session.get(Agent, agent_id)
            assert agent is not None
            agent.active_revision_id = uuid.UUID(
                f"a0000000-0000-0000-0000-{index:012d}"
            )

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
