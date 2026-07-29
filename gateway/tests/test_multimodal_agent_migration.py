"""Migration coverage for enabling spoken-image agents."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa


def _load_migration():
    path = (
        Path(__file__).parents[2]
        / "alembic"
        / "versions"
        / "015_enable_multimodal_agents.py"
    )
    spec = importlib.util.spec_from_file_location("stage11_agent_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_multimodal_agent_migration_is_idempotent_and_reversible(
    monkeypatch,
) -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    agents = sa.Table(
        "agents",
        metadata,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tools", sa.JSON(), nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            agents.insert(),
            [
                {"id": "teacher_friend", "tools": ["image_search"]},
                {"id": "outdoor_guide", "tools": ["web_search"]},
                {"id": "tech_guide", "tools": ["web_search", "image_search"]},
                {"id": "storyteller", "tools": []},
            ],
        )
        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)

        migration.upgrade()
        migration.upgrade()
        rows = {
            row.id: row.tools
            for row in connection.execute(sa.select(agents)).mappings()
        }
        assert rows["teacher_friend"] == [
            "image_search",
            "image_understanding",
        ]
        assert rows["outdoor_guide"] == ["web_search", "image_understanding"]
        assert rows["tech_guide"] == [
            "web_search",
            "image_search",
            "image_understanding",
        ]
        assert rows["storyteller"] == []

        migration.downgrade()
        rows = {
            row.id: row.tools
            for row in connection.execute(sa.select(agents)).mappings()
        }
        assert rows["teacher_friend"] == ["image_search"]
        assert rows["outdoor_guide"] == ["web_search"]
        assert rows["tech_guide"] == ["web_search", "image_search"]
        assert rows["storyteller"] == []
