"""Standalone admin panel app for Family AI Gateway."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from gateway.admin.agents_router import router as agents_router
from gateway.admin.auth import verify_admin as _verify_admin
from gateway.admin.history_schemas import (
    ConversationHistoryResponse,
    HistorySummaryResponse,
)
from gateway.admin.history_service import HistoryService
from gateway.admin.monitoring_router import router as monitoring_router
from gateway.app.config import get_settings
from gateway.app.db.session import get_session_factory


class SettingsResponse(BaseModel):
    environment: str
    message_retention_days: int
    openai_model: str
    openai_base_url: str | None
    speech_base_url: str | None
    stt_model: str
    tts_model: str
    tts_voice: str
    tts_response_format: Literal["mp3", "wav"]
    has_openai_api_key: bool
    openai_api_key_preview: str
    has_speech_api_key: bool
    speech_api_key_preview: str
    music_recognition_provider: Literal["disabled", "acrcloud"]
    acrcloud_host: str | None
    has_acrcloud_access_key: bool
    acrcloud_access_key_preview: str
    has_acrcloud_access_secret: bool
    acrcloud_access_secret_preview: str
    music_recognition_timeout_seconds: float
    must_change_password: bool


class SettingsUpdateRequest(BaseModel):
    message_retention_days: int = Field(ge=1, le=3650)
    openai_model: str = Field(min_length=1, max_length=200)
    openai_base_url: str | None = Field(default=None, max_length=500)
    speech_base_url: str | None = Field(default=None, max_length=500)
    stt_model: str = Field(min_length=1, max_length=200)
    tts_model: str = Field(min_length=1, max_length=200)
    tts_voice: str = Field(min_length=1, max_length=200)
    tts_response_format: Literal["mp3", "wav"]
    openai_api_key: str | None = Field(default=None, max_length=500)
    speech_api_key: str | None = Field(default=None, max_length=500)
    music_recognition_provider: Literal["disabled", "acrcloud"] = "disabled"
    acrcloud_host: str | None = Field(default=None, max_length=500)
    acrcloud_access_key: str | None = Field(default=None, max_length=500)
    acrcloud_access_secret: str | None = Field(default=None, max_length=500)
    music_recognition_timeout_seconds: float = Field(default=8.0, ge=1, le=30)


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _load_env_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _upsert_env_values(path: Path, updates: dict[str, str]) -> None:
    lines = _load_env_lines(path)
    remaining = dict(updates)
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue

        key, _value = line.split("=", 1)
        env_key = key.strip()
        if env_key in remaining:
            new_lines.append(f"{env_key}={remaining.pop(env_key)}")
        else:
            new_lines.append(line)

    for key, value in remaining.items():
        new_lines.append(f"{key}={value}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _must_change_password(settings: Any) -> bool:
    current_password = settings.admin_password.get_secret_value()
    return settings.admin_force_password_change or current_password == "change-me"


class ChangePasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=200)


app = FastAPI(title="Family AI Admin", version="0.1.0")
app.include_router(agents_router)
app.include_router(monitoring_router)


def get_history_session() -> Generator[Session]:
    """Yield a read-only session without committing a GET request."""

    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def get_history_service(
    session: Session = Depends(get_history_session),
) -> HistoryService:
    return HistoryService(session)


@app.get("/", response_class=HTMLResponse)
def admin_index() -> str:
    admin_page = Path(__file__).with_name("panel.html")
    return admin_page.read_text(encoding="utf-8")


@app.get("/api/settings", response_model=SettingsResponse)
def get_runtime_settings(_user: str = Depends(_verify_admin)) -> SettingsResponse:
    settings = get_settings()
    api_key = settings.openai_api_key.get_secret_value()
    speech_api_key = settings.speech_api_key.get_secret_value()
    acrcloud_access_key = settings.acrcloud_access_key.get_secret_value()
    acrcloud_access_secret = settings.acrcloud_access_secret.get_secret_value()

    return SettingsResponse(
        environment=settings.environment,
        message_retention_days=settings.message_retention_days,
        openai_model=settings.openai_model,
        openai_base_url=settings.openai_base_url,
        speech_base_url=settings.speech_base_url,
        stt_model=settings.stt_model,
        tts_model=settings.tts_model,
        tts_voice=settings.tts_voice,
        tts_response_format=settings.tts_response_format,
        has_openai_api_key=api_key not in {"", "sk-placeholder"},
        openai_api_key_preview=_mask_secret(api_key),
        has_speech_api_key=bool(speech_api_key),
        speech_api_key_preview=_mask_secret(speech_api_key),
        music_recognition_provider=settings.music_recognition_provider,
        acrcloud_host=settings.acrcloud_host,
        has_acrcloud_access_key=bool(acrcloud_access_key),
        acrcloud_access_key_preview=_mask_secret(acrcloud_access_key),
        has_acrcloud_access_secret=bool(acrcloud_access_secret),
        acrcloud_access_secret_preview=_mask_secret(acrcloud_access_secret),
        music_recognition_timeout_seconds=settings.music_recognition_timeout_seconds,
        must_change_password=_must_change_password(settings),
    )


@app.get("/api/history/summary", response_model=HistorySummaryResponse)
def get_history_summary(
    days: int = Query(default=10, ge=1, le=30),
    _user: str = Depends(_verify_admin),
    service: HistoryService = Depends(get_history_service),
) -> HistorySummaryResponse:
    """Return aggregate activity without writing or logging message content."""

    return service.get_summary(days=days)


@app.get("/api/history/conversations", response_model=ConversationHistoryResponse)
def get_conversation_history(
    days: int = Query(default=10, ge=1, le=30),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    search: str | None = Query(default=None, max_length=200),
    _user: str = Depends(_verify_admin),
    service: HistoryService = Depends(get_history_service),
) -> ConversationHistoryResponse:
    """Return retained transcripts for the protected parent viewer."""

    return service.get_conversations(
        days=days,
        page=page,
        page_size=page_size,
        search=search,
    )


@app.post("/api/settings", response_model=SettingsResponse)
def update_runtime_settings(
    payload: SettingsUpdateRequest,
    _user: str = Depends(_verify_admin),
) -> SettingsResponse:
    settings = get_settings()
    env_path = Path(settings.admin_env_file)

    updates: dict[str, str] = {
        "FAMILY_AI_MESSAGE_RETENTION_DAYS": str(payload.message_retention_days),
        "FAMILY_AI_OPENAI_MODEL": payload.openai_model.strip(),
        "FAMILY_AI_OPENAI_BASE_URL": (payload.openai_base_url or "").strip(),
        "FAMILY_AI_SPEECH_BASE_URL": (payload.speech_base_url or "").strip(),
        "FAMILY_AI_STT_MODEL": payload.stt_model.strip(),
        "FAMILY_AI_TTS_MODEL": payload.tts_model.strip(),
        "FAMILY_AI_TTS_VOICE": payload.tts_voice.strip(),
        "FAMILY_AI_TTS_RESPONSE_FORMAT": payload.tts_response_format,
        "FAMILY_AI_MUSIC_RECOGNITION_PROVIDER": payload.music_recognition_provider,
        "FAMILY_AI_ACRCLOUD_HOST": (payload.acrcloud_host or "").strip(),
        "FAMILY_AI_MUSIC_RECOGNITION_TIMEOUT_SECONDS": str(
            payload.music_recognition_timeout_seconds
        ),
    }

    if payload.openai_api_key and payload.openai_api_key.strip():
        updates["FAMILY_AI_OPENAI_API_KEY"] = payload.openai_api_key.strip()
    if payload.speech_api_key and payload.speech_api_key.strip():
        updates["FAMILY_AI_SPEECH_API_KEY"] = payload.speech_api_key.strip()
    if payload.acrcloud_access_key and payload.acrcloud_access_key.strip():
        updates["FAMILY_AI_ACRCLOUD_ACCESS_KEY"] = payload.acrcloud_access_key.strip()
    if payload.acrcloud_access_secret and payload.acrcloud_access_secret.strip():
        updates["FAMILY_AI_ACRCLOUD_ACCESS_SECRET"] = payload.acrcloud_access_secret.strip()

    _upsert_env_values(env_path, updates)

    get_settings.cache_clear()
    refreshed = get_settings()
    api_key = refreshed.openai_api_key.get_secret_value()
    speech_api_key = refreshed.speech_api_key.get_secret_value()
    acrcloud_access_key = refreshed.acrcloud_access_key.get_secret_value()
    acrcloud_access_secret = refreshed.acrcloud_access_secret.get_secret_value()

    return SettingsResponse(
        environment=refreshed.environment,
        message_retention_days=refreshed.message_retention_days,
        openai_model=refreshed.openai_model,
        openai_base_url=refreshed.openai_base_url,
        speech_base_url=refreshed.speech_base_url,
        stt_model=refreshed.stt_model,
        tts_model=refreshed.tts_model,
        tts_voice=refreshed.tts_voice,
        tts_response_format=refreshed.tts_response_format,
        has_openai_api_key=api_key not in {"", "sk-placeholder"},
        openai_api_key_preview=_mask_secret(api_key),
        has_speech_api_key=bool(speech_api_key),
        speech_api_key_preview=_mask_secret(speech_api_key),
        music_recognition_provider=refreshed.music_recognition_provider,
        acrcloud_host=refreshed.acrcloud_host,
        has_acrcloud_access_key=bool(acrcloud_access_key),
        acrcloud_access_key_preview=_mask_secret(acrcloud_access_key),
        has_acrcloud_access_secret=bool(acrcloud_access_secret),
        acrcloud_access_secret_preview=_mask_secret(acrcloud_access_secret),
        music_recognition_timeout_seconds=refreshed.music_recognition_timeout_seconds,
        must_change_password=_must_change_password(refreshed),
    )


@app.post("/api/change-password")
def change_admin_password(
    payload: ChangePasswordRequest,
    _user: str = Depends(_verify_admin),
) -> dict[str, Any]:
    new_password = payload.new_password.strip()
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    settings = get_settings()
    env_path = Path(settings.admin_env_file)

    _upsert_env_values(
        env_path,
        {
            "FAMILY_AI_ADMIN_PASSWORD": new_password,
            "FAMILY_AI_ADMIN_FORCE_PASSWORD_CHANGE": "false",
        },
    )

    get_settings.cache_clear()
    return {"status": "ok"}


@app.get("/api/healthz")
def healthz() -> dict[str, Any]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("gateway.admin.main:app", host="0.0.0.0", port=8001)
