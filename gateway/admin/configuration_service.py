"""Atomic, host-local lifecycle for the Gateway settings managed by Admin."""

from __future__ import annotations

import hashlib
import secrets
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from gateway.admin.configuration_schemas import (
    ConfigurationChange,
    ConfigurationRevisionResponse,
)
from gateway.admin.system_service import GatewayRestartError, GatewaySystemService
from gateway.app.config import Settings

MANAGED_CONFIGURATION_KEYS = frozenset(
    {
        "FAMILY_AI_MESSAGE_RETENTION_DAYS",
        "FAMILY_AI_OPENAI_MODEL",
        "FAMILY_AI_OPENAI_BASE_URL",
        "FAMILY_AI_OPENAI_API_KEY",
        "FAMILY_AI_SPEECH_BASE_URL",
        "FAMILY_AI_SPEECH_API_KEY",
        "FAMILY_AI_STT_BASE_URL",
        "FAMILY_AI_STT_MODEL",
        "FAMILY_AI_STT_INITIAL_PROMPT",
        "FAMILY_AI_STT_API_KEY",
        "FAMILY_AI_TTS_BASE_URL",
        "FAMILY_AI_TTS_MODEL",
        "FAMILY_AI_TTS_VOICE",
        "FAMILY_AI_TTS_RESPONSE_FORMAT",
        "FAMILY_AI_TTS_API_KEY",
        "FAMILY_AI_WEB_SEARCH_TOOL_TYPE",
        "FAMILY_AI_IMAGE_SEARCH_PROVIDER",
        "FAMILY_AI_IMAGE_SEARCH_TIMEOUT_SECONDS",
        "FAMILY_AI_VISION_PROVIDER",
        "FAMILY_AI_VISION_BASE_URL",
        "FAMILY_AI_VISION_MODEL",
        "FAMILY_AI_VISION_MAX_IMAGE_BYTES",
        "FAMILY_AI_VISION_API_KEY",
        "FAMILY_AI_MUSIC_RECOGNITION_PROVIDER",
        "FAMILY_AI_ACRCLOUD_HOST",
        "FAMILY_AI_ACRCLOUD_ACCESS_KEY",
        "FAMILY_AI_ACRCLOUD_ACCESS_SECRET",
        "FAMILY_AI_MUSIC_RECOGNITION_TIMEOUT_SECONDS",
        "FAMILY_AI_VOICE_MAX_IN_FLIGHT",
        "FAMILY_AI_VOICE_STT_TIMEOUT_SECONDS",
        "FAMILY_AI_VOICE_LLM_TIMEOUT_SECONDS",
        "FAMILY_AI_VOICE_TTS_TIMEOUT_SECONDS",
    }
)

SECRET_KEYS = frozenset(
    key
    for key in MANAGED_CONFIGURATION_KEYS
    if any(marker in key for marker in ("API_KEY", "ACCESS_KEY", "SECRET", "TOKEN"))
)


class ConfigurationValidationError(RuntimeError):
    """Raised when candidate values do not form a valid Gateway configuration."""


class ConfigurationApplyError(RuntimeError):
    """Raised after a failed apply has been restored to its previous values."""


class ConfigurationRevisionNotFoundError(RuntimeError):
    """Raised when an unknown or incomplete revision is selected."""


class GatewayConfigurationService:
    """Validate, version, apply and recover the managed Gateway environment."""

    _lock = threading.Lock()

    def __init__(
        self,
        *,
        env_path: Path,
        history_dir: Path,
        settings: Settings,
        system_service: GatewaySystemService | None = None,
        max_revisions: int = 20,
    ) -> None:
        self._env_path = env_path
        self._history_dir = history_dir
        self._settings = settings
        self._system_service = system_service or GatewaySystemService()
        self._max_revisions = max_revisions

    def preview(self, updates: Mapping[str, str]) -> list[ConfigurationChange]:
        current = self._read_env()
        candidate = self._candidate_values(current, updates)
        self._validate(candidate)
        return self._changes(self._managed_values(current), candidate)

    def apply(
        self,
        updates: Mapping[str, str],
        *,
        actor: str,
    ) -> ConfigurationRevisionResponse | None:
        with self._lock:
            current = self._read_env()
            candidate = self._candidate_values(current, updates)
            self._validate(candidate)
            changes = self._changes(self._managed_values(current), candidate)
            if not changes:
                return None

            self._ensure_baseline(current, actor=actor)
            previous_bytes = self._env_path.read_bytes() if self._env_path.exists() else None
            candidate_text = self._render_full_env(current, candidate)
            revision = self._new_revision(
                actor=actor,
                operation="apply",
                status="active",
                managed_values=candidate,
                changes=changes,
            )
            try:
                self._write_env_atomic(candidate_text)
            except OSError as exc:
                failed = revision.model_copy(update={"status": "rolled_back"})
                self._persist_revision(failed, candidate, store_snapshot=False)
                raise ConfigurationApplyError(
                    "Gateway configuration could not be persisted"
                ) from exc
            try:
                self._system_service.restart_gateway_verified()
            except GatewayRestartError as exc:
                self._restore_full_env(previous_bytes)
                self._recover_gateway()
                failed = revision.model_copy(update={"status": "rolled_back"})
                self._persist_revision(failed, candidate, store_snapshot=False)
                raise ConfigurationApplyError(
                    "Gateway rejected the requested configuration and was restored"
                ) from exc

            self._mark_active_revision_superseded(except_id=revision.id)
            self._persist_revision(revision, candidate)
            self._prune_history()
            return revision

    def list_revisions(self) -> list[ConfigurationRevisionResponse]:
        if not self._history_dir.exists():
            return []
        revisions: list[ConfigurationRevisionResponse] = []
        for path in self._history_dir.glob("*.json"):
            try:
                revisions.append(
                    ConfigurationRevisionResponse.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                )
            except (OSError, ValidationError, ValueError):
                continue
        return sorted(revisions, key=lambda item: item.created_at, reverse=True)

    def rollback(
        self,
        revision_id: str,
        *,
        actor: str,
    ) -> ConfigurationRevisionResponse:
        with self._lock:
            target = self._load_snapshot(revision_id)
            current = self._read_env()
            candidate = dict(current)
            candidate.update(target)
            candidate = self._managed_values(candidate)
            self._validate(candidate)
            changes = self._changes(self._managed_values(current), candidate)
            if not changes:
                raise ConfigurationValidationError("Selected revision is already active")

            previous_bytes = self._env_path.read_bytes() if self._env_path.exists() else None
            candidate_text = self._render_full_env(current, candidate)
            applied = self._new_revision(
                actor=actor,
                operation="rollback",
                status="active",
                managed_values=candidate,
                changes=changes,
                source_revision_id=revision_id,
            )
            try:
                self._write_env_atomic(candidate_text)
            except OSError as exc:
                failed = applied.model_copy(update={"status": "rolled_back"})
                self._persist_revision(failed, candidate, store_snapshot=False)
                raise ConfigurationApplyError(
                    "Gateway configuration could not be persisted"
                ) from exc
            try:
                self._system_service.restart_gateway_verified()
            except GatewayRestartError as exc:
                self._restore_full_env(previous_bytes)
                self._recover_gateway()
                failed = applied.model_copy(update={"status": "rolled_back"})
                self._persist_revision(failed, candidate, store_snapshot=False)
                raise ConfigurationApplyError(
                    "Gateway rejected the selected revision and was restored"
                ) from exc

            self._mark_active_revision_superseded(except_id=applied.id)
            self._persist_revision(applied, candidate)
            self._prune_history()
            return applied

    def _candidate_values(
        self,
        current: Mapping[str, str],
        updates: Mapping[str, str],
    ) -> dict[str, str]:
        unexpected = set(updates) - MANAGED_CONFIGURATION_KEYS
        if unexpected:
            raise ConfigurationValidationError("Unmanaged configuration field")
        if any(
            character in value
            for value in updates.values()
            for character in "\r\n\0"
        ):
            raise ConfigurationValidationError("Configuration values must be single-line")
        candidate = self._managed_values(current)
        candidate.update(updates)
        return candidate

    def _validate(self, candidate: Mapping[str, str]) -> None:
        values = self._settings.model_dump()
        for field_name in Settings.model_fields:
            env_key = f"FAMILY_AI_{field_name.upper()}"
            if env_key in candidate:
                values[field_name] = candidate[env_key]
        try:
            Settings.model_validate(values)
        except ValidationError as exc:
            raise ConfigurationValidationError("Candidate configuration is invalid") from exc

    def _read_env(self) -> dict[str, str]:
        if not self._env_path.exists():
            return {}
        return parse_env_text(self._env_path.read_text(encoding="utf-8"))

    def _managed_values(self, values: Mapping[str, str]) -> dict[str, str]:
        managed: dict[str, str] = {}
        for key in sorted(MANAGED_CONFIGURATION_KEYS):
            if key in values:
                managed[key] = values[key]
                continue
            field_name = key.removeprefix("FAMILY_AI_").lower()
            value = getattr(self._settings, field_name)
            if hasattr(value, "get_secret_value"):
                value = value.get_secret_value()
            if value is None:
                managed[key] = ""
            elif isinstance(value, bool):
                managed[key] = str(value).lower()
            else:
                managed[key] = str(value)
        return managed

    def _changes(
        self,
        current: Mapping[str, str],
        candidate: Mapping[str, str],
    ) -> list[ConfigurationChange]:
        changes: list[ConfigurationChange] = []
        for key in sorted(MANAGED_CONFIGURATION_KEYS):
            before = current.get(key, "")
            after = candidate.get(key, "")
            if before == after:
                continue
            secret = key in SECRET_KEYS
            changes.append(
                ConfigurationChange(
                    key=key.removeprefix("FAMILY_AI_").lower(),
                    before=self._display_value(before, secret=secret),
                    after=self._display_value(after, secret=secret),
                    secret=secret,
                )
            )
        return changes

    @staticmethod
    def _display_value(value: str, *, secret: bool) -> str:
        if secret:
            return "настроен" if value else "не настроен"
        if not value:
            return "—"
        return value if len(value) <= 120 else f"{value[:117]}..."

    def _render_full_env(
        self,
        current: Mapping[str, str],
        managed: Mapping[str, str],
    ) -> str:
        lines = (
            self._env_path.read_text(encoding="utf-8").splitlines()
            if self._env_path.exists()
            else []
        )
        return render_env_updates(lines, managed)

    def _write_env_atomic(self, content: str) -> None:
        self._env_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._env_path.with_name(
            f".{self._env_path.name}.{secrets.token_hex(4)}.tmp"
        )
        try:
            temporary.write_text(content, encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(self._env_path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _restore_full_env(self, previous: bytes | None) -> None:
        if previous is None:
            self._env_path.unlink(missing_ok=True)
            return
        temporary = self._env_path.with_name(f".{self._env_path.name}.rollback")
        temporary.write_bytes(previous)
        temporary.chmod(0o600)
        temporary.replace(self._env_path)

    def _recover_gateway(self) -> None:
        try:
            self._system_service.restart_gateway_verified()
        except GatewayRestartError as exc:
            raise ConfigurationApplyError(
                "Gateway configuration was restored but readiness did not recover"
            ) from exc

    def _ensure_baseline(self, current: Mapping[str, str], *, actor: str) -> None:
        managed = self._managed_values(current)
        fingerprint = self._fingerprint(managed)
        if any(item.fingerprint == fingerprint for item in self.list_revisions()):
            return
        baseline = self._new_revision(
            actor=actor,
            operation="baseline",
            status="active",
            managed_values=managed,
            changes=[],
        )
        self._persist_revision(baseline, managed)

    def _new_revision(
        self,
        *,
        actor: str,
        operation: str,
        status: str,
        managed_values: Mapping[str, str],
        changes: list[ConfigurationChange],
        source_revision_id: str | None = None,
    ) -> ConfigurationRevisionResponse:
        created_at = datetime.now(UTC)
        revision_id = f"{created_at:%Y%m%dT%H%M%S}-{secrets.token_hex(3)}"
        return ConfigurationRevisionResponse(
            id=revision_id,
            created_at=created_at,
            actor=actor,
            operation=operation,
            status=status,
            fingerprint=self._fingerprint(managed_values),
            source_revision_id=source_revision_id,
            changes=changes,
        )

    @staticmethod
    def _fingerprint(values: Mapping[str, str]) -> str:
        serialized = "\n".join(f"{key}={values[key]}" for key in sorted(values))
        return hashlib.sha256(serialized.encode()).hexdigest()[:12]

    def _persist_revision(
        self,
        revision: ConfigurationRevisionResponse,
        managed_values: Mapping[str, str],
        *,
        store_snapshot: bool = True,
    ) -> None:
        self._history_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._history_dir.chmod(0o700)
        except OSError:
            pass
        if store_snapshot:
            snapshot = self._snapshot_path(revision.id)
            snapshot.write_text(
                "".join(
                    f"{key}={managed_values.get(key, '')}\n"
                    for key in sorted(MANAGED_CONFIGURATION_KEYS)
                ),
                encoding="utf-8",
            )
            snapshot.chmod(0o600)
        self._write_metadata_atomic(revision)

    def _write_metadata_atomic(self, revision: ConfigurationRevisionResponse) -> None:
        metadata = self._metadata_path(revision.id)
        temporary = metadata.with_suffix(".json.tmp")
        temporary.write_text(
            revision.model_dump_json(indent=2),
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        temporary.replace(metadata)

    def _mark_active_revision_superseded(self, *, except_id: str) -> None:
        for revision in self.list_revisions():
            if revision.id == except_id or revision.status != "active":
                continue
            updated = revision.model_copy(update={"status": "superseded"})
            self._write_metadata_atomic(updated)

    def _load_snapshot(self, revision_id: str) -> dict[str, str]:
        allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        if not revision_id or any(character not in allowed for character in revision_id):
            raise ConfigurationRevisionNotFoundError("Configuration revision not found")
        path = self._snapshot_path(revision_id)
        metadata_path = self._metadata_path(revision_id)
        if not path.is_file() or not metadata_path.is_file():
            raise ConfigurationRevisionNotFoundError("Configuration revision not found")
        try:
            revision = ConfigurationRevisionResponse.model_validate_json(
                metadata_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise ConfigurationRevisionNotFoundError(
                "Configuration revision not found"
            ) from exc
        if revision.status == "rolled_back":
            raise ConfigurationRevisionNotFoundError("Configuration revision not found")
        return self._managed_values(parse_env_text(path.read_text(encoding="utf-8")))

    def _prune_history(self) -> None:
        revisions = self.list_revisions()
        for revision in revisions[self._max_revisions :]:
            self._metadata_path(revision.id).unlink(missing_ok=True)
            self._snapshot_path(revision.id).unlink(missing_ok=True)

    def _metadata_path(self, revision_id: str) -> Path:
        return self._history_dir / f"{revision_id}.json"

    def _snapshot_path(self, revision_id: str) -> Path:
        return self._history_dir / f"{revision_id}.env"


def parse_env_text(text: str) -> dict[str, str]:
    """Parse the simple KEY=VALUE format written by the Admin control plane."""

    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = _strip_matching_quotes(value.strip())
    return values


def render_env_updates(lines: list[str], updates: Mapping[str, str]) -> str:
    """Render updates without changing unrelated lines or comments."""

    if any(
        character in value
        for value in updates.values()
        for character in "\r\n\0"
    ):
        raise ValueError("environment values must be single-line")
    remaining = dict(updates)
    rendered: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            rendered.append(line)
            continue
        key, _value = line.split("=", 1)
        env_key = key.strip()
        if env_key in remaining:
            rendered.append(f"{env_key}={remaining.pop(env_key)}")
        else:
            rendered.append(line)
    rendered.extend(f"{key}={value}" for key, value in remaining.items())
    return "\n".join(rendered) + "\n"


def _strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
