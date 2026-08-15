"""Release passport aggregation tests."""

from types import SimpleNamespace

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from gateway.admin.release_passport_service import ReleasePassportService
from gateway.app.config import Settings
from gateway.app.observability.runtime_identity import configuration_fingerprint


class StubVoiceObservability:
    def __init__(self, speech_data: dict[str, object] | None) -> None:
        self._speech_data = speech_data

    def get_snapshot(self):
        status = "healthy" if self._speech_data else "down"
        return SimpleNamespace(speech=SimpleNamespace(status=status, data=self._speech_data))


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    session = Session(engine)
    session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL)"))
    session.execute(text("INSERT INTO alembic_version VALUES ('head-1')"))
    session.commit()
    return session


def test_release_passport_reports_aligned_runtime(monkeypatch) -> None:
    settings = Settings(environment="test")
    commit = "c" * 40
    gateway = {
        "app_version": "0.1.0",
        "actual_commit": commit,
        "expected_commit": commit,
        "matches_expected": True,
        "uptime_seconds": 20,
        "config_fingerprint": configuration_fingerprint(settings),
        "android": {
            "version": "1.6.0+8",
            "source_commit": commit,
            "observed_at": "2026-08-15T12:00:00+00:00",
        },
    }
    speech = {
        "uptime_seconds": 30,
        "runtime": {
            "app_version": "0.1.0",
            "actual_commit": commit,
            "expected_commit": commit,
            "matches_expected": True,
        },
    }
    session = _session()
    service = ReleasePassportService(
        settings,
        session,
        StubVoiceObservability(speech),
        code_head_provider=lambda: "head-1",
    )
    monkeypatch.setattr(service, "_fetch_gateway_identity", lambda: gateway)

    passport = service.get_passport()

    assert passport.status == "aligned"
    assert passport.database.current_revision == "head-1"
    assert passport.android.version == "1.6.0+8"
    assert passport.configuration.fingerprint == configuration_fingerprint(settings)
    session.close()


def test_release_passport_marks_commit_and_schema_drift(monkeypatch) -> None:
    settings = Settings(environment="test")
    gateway = {
        "actual_commit": "a" * 40,
        "expected_commit": "b" * 40,
        "matches_expected": False,
        "config_fingerprint": "0" * 64,
    }
    session = _session()
    service = ReleasePassportService(
        settings,
        session,
        StubVoiceObservability(None),
        code_head_provider=lambda: "head-2",
    )
    monkeypatch.setattr(service, "_fetch_gateway_identity", lambda: gateway)

    passport = service.get_passport()

    assert passport.status == "drift"
    assert passport.gateway.status == "drift"
    assert passport.database.status == "drift"
    assert passport.configuration.status == "drift"
    session.close()
