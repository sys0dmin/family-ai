"""Aggregate immutable release and schema identity without exposing secrets."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from gateway.admin.release_passport_schemas import (
    AndroidReleaseIdentity,
    ComponentReleaseIdentity,
    ConfigurationIdentity,
    DatabaseReleaseIdentity,
    PassportStatus,
    ReleasePassportResponse,
)
from gateway.admin.voice_observability_service import VoiceObservabilityService
from gateway.app.config import Settings
from gateway.app.observability.runtime_identity import configuration_fingerprint


def _active_code_head() -> str | None:
    config_path = Path.cwd() / "alembic.ini"
    if not config_path.is_file():
        return None
    try:
        heads = ScriptDirectory.from_config(AlembicConfig(str(config_path))).get_heads()
    except (OSError, ValueError):
        return None
    return heads[0] if len(heads) == 1 else None


class ReleasePassportService:
    """Build one current, privacy-safe version snapshot for Admin."""

    def __init__(
        self,
        settings: Settings,
        session: Session,
        voice_observability: VoiceObservabilityService,
        *,
        code_head_provider: Callable[[], str | None] = _active_code_head,
    ) -> None:
        self._settings = settings
        self._session = session
        self._voice_observability = voice_observability
        self._code_head_provider = code_head_provider

    def get_passport(self) -> ReleasePassportResponse:
        gateway_payload = self._fetch_gateway_identity()
        voice = self._voice_observability.get_snapshot()
        speech_payload = voice.speech.data if voice.speech.status == "healthy" else None
        speech_runtime = speech_payload.get("runtime") if isinstance(speech_payload, dict) else None

        gateway = self._component("gateway", gateway_payload)
        speech = self._component(
            "speech",
            speech_runtime if isinstance(speech_runtime, dict) else None,
            uptime=(speech_payload or {}).get("uptime_seconds")
            if isinstance(speech_payload, dict)
            else None,
        )
        database = self._database()
        configuration = self._configuration(gateway_payload)
        android = self._android(gateway_payload)
        statuses: list[PassportStatus] = [
            gateway.status,
            speech.status,
            database.status,
            configuration.status,
        ]
        if "drift" in statuses:
            overall: PassportStatus = "drift"
        elif "unavailable" in statuses or android.status == "unavailable":
            overall = "unavailable"
        else:
            overall = "aligned"
        return ReleasePassportResponse(
            status=overall,
            checked_at=datetime.now(UTC),
            gateway=gateway,
            speech=speech,
            database=database,
            android=android,
            configuration=configuration,
        )

    def _fetch_gateway_identity(self) -> dict[str, object] | None:
        url = self._settings.gateway_runtime_identity_url
        if not url:
            return None
        try:
            with urlopen(  # noqa: S310
                Request(url, headers={"Accept": "application/json"}),
                timeout=self._settings.monitoring_request_timeout_seconds,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _component(
        component: str,
        payload: dict[str, object] | None,
        *,
        uptime: object = None,
    ) -> ComponentReleaseIdentity:
        if payload is None:
            return ComponentReleaseIdentity(component=component, status="unavailable")
        matches = payload.get("matches_expected")
        status: PassportStatus = (
            "aligned" if matches is True else "drift" if matches is False else "unavailable"
        )
        runtime_uptime = payload.get("uptime_seconds", uptime)
        return ComponentReleaseIdentity(
            component=component,
            status=status,
            app_version=payload.get("app_version")
            if isinstance(payload.get("app_version"), str)
            else None,
            actual_commit=payload.get("actual_commit")
            if isinstance(payload.get("actual_commit"), str)
            else None,
            expected_commit=payload.get("expected_commit")
            if isinstance(payload.get("expected_commit"), str)
            else None,
            uptime_seconds=float(runtime_uptime)
            if isinstance(runtime_uptime, (int, float))
            else None,
        )

    def _database(self) -> DatabaseReleaseIdentity:
        code_head = self._code_head_provider()
        try:
            rows = (
                self._session.execute(text("SELECT version_num FROM alembic_version"))
                .scalars()
                .all()
            )
        except SQLAlchemyError:
            self._session.rollback()
            return DatabaseReleaseIdentity(status="unavailable", code_head=code_head)
        current = rows[0] if len(rows) == 1 else None
        if current is None or code_head is None:
            status: PassportStatus = "unavailable"
        else:
            status = "aligned" if current == code_head else "drift"
        return DatabaseReleaseIdentity(
            status=status,
            current_revision=current,
            code_head=code_head,
        )

    def _configuration(self, payload: dict[str, object] | None) -> ConfigurationIdentity:
        actual = payload.get("config_fingerprint") if payload else None
        if not isinstance(actual, str):
            return ConfigurationIdentity(status="unavailable")
        expected = configuration_fingerprint(self._settings)
        return ConfigurationIdentity(
            status="aligned" if actual == expected else "drift",
            fingerprint=actual,
        )

    @staticmethod
    def _android(payload: dict[str, object] | None) -> AndroidReleaseIdentity:
        android = payload.get("android") if payload else None
        if not isinstance(android, dict):
            return AndroidReleaseIdentity(status="unavailable")
        try:
            return AndroidReleaseIdentity(status="observed", **android)
        except (TypeError, ValueError):
            return AndroidReleaseIdentity(status="unavailable")
