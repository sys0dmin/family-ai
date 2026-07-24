"""Persistent, narrowly-scoped runtime settings for the Speech Service."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


class RuntimeSettingsApplyError(RuntimeError):
    """Raised when settings could not be persisted or restart was rejected."""


class SpeechRuntimeSettingsManager:
    """Atomically persist only approved STT settings and schedule a restart."""

    def __init__(
        self,
        path: Path,
        restart_request_path: Path,
        restart_scheduler: Callable[[], None] | None = None,
    ) -> None:
        self._path = path
        self._restart_request_path = restart_request_path
        self._restart_scheduler = restart_scheduler or self._request_restart

    def apply(self, *, beam_size: int, vad_filter: bool) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        previous = self._path.read_bytes() if self._path.exists() else None
        temporary = self._path.with_suffix(".tmp")
        content = (
            f"FAMILY_AI_SPEECH_STT_BEAM_SIZE={beam_size}\n"
            f"FAMILY_AI_SPEECH_STT_VAD_FILTER={str(vad_filter).lower()}\n"
        )
        try:
            temporary.write_text(content, encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(self._path)
            self._restart_scheduler()
        except (OSError, RuntimeSettingsApplyError):
            temporary.unlink(missing_ok=True)
            self._restore(previous)
            raise

    def _restore(self, previous: bytes | None) -> None:
        if previous is None:
            self._path.unlink(missing_ok=True)
            return
        temporary = self._path.with_suffix(".rollback")
        temporary.write_bytes(previous)
        temporary.chmod(0o600)
        temporary.replace(self._path)

    def _request_restart(self) -> None:
        try:
            self._restart_request_path.touch(exist_ok=True)
        except OSError as exc:
            raise RuntimeSettingsApplyError("Speech restart could not be scheduled") from exc
