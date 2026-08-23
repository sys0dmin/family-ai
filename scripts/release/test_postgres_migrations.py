"""Exercise the complete Alembic chain in a temporary PostgreSQL database."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url


def _run_alembic(repo: Path, database_url: str, *arguments: str) -> None:
    environment = os.environ.copy()
    environment["FAMILY_AI_DATABASE_URL"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(repo / "alembic.ini"), *arguments],
        cwd=repo,
        env=environment,
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--admin-url",
        default=os.getenv("FAMILY_AI_MIGRATION_TEST_ADMIN_URL"),
        help="PostgreSQL admin URL ending in /postgres or /template1",
    )
    args = parser.parse_args()
    if not args.admin_url:
        parser.error("--admin-url or FAMILY_AI_MIGRATION_TEST_ADMIN_URL is required")

    admin_url = make_url(args.admin_url)
    if admin_url.drivername.split("+", 1)[0] != "postgresql":
        parser.error("migration test requires PostgreSQL")
    if admin_url.database not in {"postgres", "template1"}:
        parser.error("admin URL must target postgres or template1, never the application database")

    database_name = f"family_ai_migration_test_{uuid.uuid4().hex[:12]}"
    test_url = admin_url.set(database=database_name).render_as_string(hide_password=False)
    repo = args.repo.resolve()
    connection_parameters = args.admin_url.replace("postgresql+psycopg://", "postgresql://")

    with psycopg.connect(connection_parameters, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        _run_alembic(repo, test_url, "upgrade", "head")
        _run_alembic(repo, test_url, "downgrade", "base")
        _run_alembic(repo, test_url, "upgrade", "head")
        test_parameters = test_url.replace("postgresql+psycopg://", "postgresql://")
        with psycopg.connect(test_parameters) as connection:
            version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            table_count = connection.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            ).fetchone()
            if not version or not table_count or table_count[0] < 2:
                raise RuntimeError("Alembic did not create the expected schema")
            print(f"Disposable PostgreSQL schema reached Alembic head {version[0]}.")
    finally:
        with psycopg.connect(connection_parameters, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database_name,),
            )
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database_name))
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
