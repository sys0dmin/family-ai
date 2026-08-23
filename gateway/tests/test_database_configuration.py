"""Database configuration fails closed outside explicit test wiring."""

from pathlib import Path

import pytest

from gateway.app.config import get_settings
from gateway.app.db.session import get_engine, reset_database_runtime


def test_database_url_must_be_configured_explicitly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FAMILY_AI_DATABASE_URL", raising=False)
    monkeypatch.delenv("FAMILY_AI_ADMIN_ENV_FILE", raising=False)
    get_settings.cache_clear()
    reset_database_runtime()

    with pytest.raises(RuntimeError, match="FAMILY_AI_DATABASE_URL is required"):
        get_engine()

    reset_database_runtime()
    get_settings.cache_clear()
