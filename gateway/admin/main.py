"""Standalone admin panel app for Family AI Gateway."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from gateway.admin.activity_router import router as activity_router
from gateway.admin.agents_router import router as agents_router
from gateway.admin.auth import (
    SESSION_COOKIE,
    create_session_token,
)
from gateway.admin.auth import (
    verify_admin as _verify_admin,
)
from gateway.admin.calibration_router import router as calibration_router
from gateway.admin.configuration_schemas import (
    ConfigurationPreviewResponse,
    ConfigurationRevisionCollection,
    ConfigurationRollbackResponse,
)
from gateway.admin.configuration_service import (
    ConfigurationApplyError,
    ConfigurationRevisionNotFoundError,
    ConfigurationValidationError,
    GatewayConfigurationService,
    render_env_updates,
)
from gateway.admin.diagnostics_router import router as diagnostics_router
from gateway.admin.history_schemas import (
    ConversationHistoryResponse,
    HistorySummaryResponse,
)
from gateway.admin.history_service import HistoryService
from gateway.admin.memory_router import router as memory_router
from gateway.admin.monitoring_router import router as monitoring_router
from gateway.admin.quality_router import router as quality_router
from gateway.admin.safety_policy_router import router as safety_policy_router
from gateway.admin.speech_runtime_router import router as speech_runtime_router
from gateway.admin.studio_router import router as studio_router
from gateway.admin.system_router import router as system_router
from gateway.admin.voice_observability_router import router as voice_observability_router
from gateway.app.config import get_settings
from gateway.app.db.session import get_session_factory


class RevalidatingStaticFiles(StaticFiles):
    """Prevent stale Admin modules from surviving a release switch."""

    async def get_response(self, path: str, scope: dict[str, Any]) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


class SettingsResponse(BaseModel):
    environment: str
    message_retention_days: int
    openai_model: str
    openai_base_url: str | None
    speech_base_url: str | None
    stt_base_url: str | None
    stt_model: str
    stt_initial_prompt: str
    tts_base_url: str | None
    tts_model: str
    tts_voice: str
    tts_response_format: Literal["mp3", "wav"]
    web_search_tool_type: Literal["disabled", "browser_search"]
    image_search_provider: Literal["disabled", "openverse"]
    image_search_timeout_seconds: float
    vision_provider: Literal["disabled", "openai_compatible"]
    vision_base_url: str | None
    vision_model: str
    vision_max_image_bytes: int
    has_vision_api_key: bool
    vision_api_key_preview: str
    has_openai_api_key: bool
    openai_api_key_preview: str
    has_speech_api_key: bool
    speech_api_key_preview: str
    has_stt_api_key: bool
    stt_api_key_preview: str
    has_tts_api_key: bool
    tts_api_key_preview: str
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
    stt_base_url: str | None = Field(default=None, max_length=500)
    stt_model: str = Field(min_length=1, max_length=200)
    stt_initial_prompt: str = Field(min_length=1, max_length=1000)
    tts_base_url: str | None = Field(default=None, max_length=500)
    tts_model: str = Field(min_length=1, max_length=200)
    tts_voice: str = Field(min_length=1, max_length=200)
    tts_response_format: Literal["mp3", "wav"]
    web_search_tool_type: Literal["disabled", "browser_search"] = "disabled"
    image_search_provider: Literal["disabled", "openverse"] = "disabled"
    image_search_timeout_seconds: float = Field(default=6.0, ge=1, le=30)
    vision_provider: Literal["disabled", "openai_compatible"] = "disabled"
    vision_base_url: str | None = Field(default=None, max_length=500)
    vision_model: str = Field(min_length=1, max_length=200)
    vision_max_image_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1024 * 1024,
        le=14 * 1024 * 1024,
    )
    vision_api_key: str | None = Field(default=None, max_length=500)
    clear_vision_api_key: bool = False
    openai_api_key: str | None = Field(default=None, max_length=500)
    speech_api_key: str | None = Field(default=None, max_length=500)
    stt_api_key: str | None = Field(default=None, max_length=500)
    tts_api_key: str | None = Field(default=None, max_length=500)
    clear_stt_api_key: bool = False
    clear_tts_api_key: bool = False
    music_recognition_provider: Literal["disabled", "acrcloud"] = "disabled"
    acrcloud_host: str | None = Field(default=None, max_length=500)
    acrcloud_access_key: str | None = Field(default=None, max_length=500)
    acrcloud_access_secret: str | None = Field(default=None, max_length=500)
    music_recognition_timeout_seconds: float = Field(default=8.0, ge=1, le=30)

    @field_validator("*", mode="before")
    @classmethod
    def reject_multiline_environment_values(cls, value: Any) -> Any:
        if isinstance(value, str) and any(character in value for character in "\r\n\0"):
            raise ValueError("configuration values must be single-line")
        return value


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
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(render_env_updates(lines, updates), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def _must_change_password(settings: Any) -> bool:
    current_password = settings.admin_password.get_secret_value()
    return settings.admin_force_password_change or current_password == "change-me"


class ChangePasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=200)

    @field_validator("new_password")
    @classmethod
    def reject_multiline_password(cls, value: str) -> str:
        if any(character in value for character in "\r\n\0"):
            raise ValueError("password must be single-line")
        return value


app = FastAPI(title="Family AI Admin", version="0.1.0")
app.mount(
    "/admin-assets",
    RevalidatingStaticFiles(directory=Path(__file__).with_name("static")),
    name="admin-assets",
)
app.include_router(agents_router)
app.include_router(activity_router)
app.include_router(monitoring_router)
app.include_router(system_router)
app.include_router(studio_router)
app.include_router(voice_observability_router)
app.include_router(calibration_router)
app.include_router(diagnostics_router)
app.include_router(speech_runtime_router)
app.include_router(safety_policy_router)
app.include_router(memory_router)
app.include_router(quality_router)


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


def get_gateway_configuration_service() -> GatewayConfigurationService:
    settings = get_settings()
    return GatewayConfigurationService(
        env_path=Path(settings.admin_env_file),
        history_dir=Path(settings.admin_config_history_dir),
        settings=settings,
    )


@app.get("/", response_class=HTMLResponse)
def admin_index() -> HTMLResponse:
    admin_page = Path(__file__).with_name("panel.html")
    return HTMLResponse(
        admin_page.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/session", status_code=204)
def create_admin_session(
    request: Request,
    response: Response,
    _user: str = Depends(_verify_admin),
) -> None:
    """Exchange Basic credentials for an HttpOnly same-origin browser session."""

    settings = get_settings()
    max_age = settings.admin_session_ttl_hours * 3600
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session_token(
            settings.admin_username,
            settings.admin_password.get_secret_value(),
        ),
        max_age=max_age,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path="/",
    )


@app.delete("/api/session", status_code=204)
def delete_admin_session(response: Response) -> None:
    """Forget the current browser session."""

    response.delete_cookie(
        key=SESSION_COOKIE,
        httponly=True,
        samesite="strict",
        path="/",
    )


def _settings_response(settings: Any) -> SettingsResponse:
    api_key = settings.openai_api_key.get_secret_value()
    speech_api_key = settings.speech_api_key.get_secret_value()
    stt_api_key = settings.stt_api_key.get_secret_value()
    tts_api_key = settings.tts_api_key.get_secret_value()
    vision_api_key = settings.vision_api_key.get_secret_value()
    acrcloud_access_key = settings.acrcloud_access_key.get_secret_value()
    acrcloud_access_secret = settings.acrcloud_access_secret.get_secret_value()

    return SettingsResponse(
        environment=settings.environment,
        message_retention_days=settings.message_retention_days,
        openai_model=settings.openai_model,
        openai_base_url=settings.openai_base_url,
        speech_base_url=settings.speech_base_url,
        stt_base_url=settings.stt_base_url,
        stt_model=settings.stt_model,
        stt_initial_prompt=settings.stt_initial_prompt,
        tts_base_url=settings.tts_base_url,
        tts_model=settings.tts_model,
        tts_voice=settings.tts_voice,
        tts_response_format=settings.tts_response_format,
        web_search_tool_type=settings.web_search_tool_type,
        image_search_provider=settings.image_search_provider,
        image_search_timeout_seconds=settings.image_search_timeout_seconds,
        vision_provider=settings.vision_provider,
        vision_base_url=settings.vision_base_url,
        vision_model=settings.vision_model,
        vision_max_image_bytes=settings.vision_max_image_bytes,
        has_vision_api_key=bool(vision_api_key),
        vision_api_key_preview=_mask_secret(vision_api_key),
        has_openai_api_key=api_key not in {"", "sk-placeholder"},
        openai_api_key_preview=_mask_secret(api_key),
        has_speech_api_key=bool(speech_api_key),
        speech_api_key_preview=_mask_secret(speech_api_key),
        has_stt_api_key=bool(stt_api_key),
        stt_api_key_preview=_mask_secret(stt_api_key),
        has_tts_api_key=bool(tts_api_key),
        tts_api_key_preview=_mask_secret(tts_api_key),
        music_recognition_provider=settings.music_recognition_provider,
        acrcloud_host=settings.acrcloud_host,
        has_acrcloud_access_key=bool(acrcloud_access_key),
        acrcloud_access_key_preview=_mask_secret(acrcloud_access_key),
        has_acrcloud_access_secret=bool(acrcloud_access_secret),
        acrcloud_access_secret_preview=_mask_secret(acrcloud_access_secret),
        music_recognition_timeout_seconds=settings.music_recognition_timeout_seconds,
        must_change_password=_must_change_password(settings),
    )


@app.get("/api/settings", response_model=SettingsResponse)
def get_runtime_settings(_user: str = Depends(_verify_admin)) -> SettingsResponse:
    return _settings_response(get_settings())


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


def _settings_updates(payload: SettingsUpdateRequest) -> dict[str, str]:
    updates: dict[str, str] = {
        "FAMILY_AI_MESSAGE_RETENTION_DAYS": str(payload.message_retention_days),
        "FAMILY_AI_OPENAI_MODEL": payload.openai_model.strip(),
        "FAMILY_AI_OPENAI_BASE_URL": (payload.openai_base_url or "").strip(),
        "FAMILY_AI_SPEECH_BASE_URL": (payload.speech_base_url or "").strip(),
        "FAMILY_AI_STT_BASE_URL": (payload.stt_base_url or "").strip(),
        "FAMILY_AI_STT_MODEL": payload.stt_model.strip(),
        "FAMILY_AI_STT_INITIAL_PROMPT": payload.stt_initial_prompt.strip(),
        "FAMILY_AI_TTS_BASE_URL": (payload.tts_base_url or "").strip(),
        "FAMILY_AI_TTS_MODEL": payload.tts_model.strip(),
        "FAMILY_AI_TTS_VOICE": payload.tts_voice.strip(),
        "FAMILY_AI_TTS_RESPONSE_FORMAT": payload.tts_response_format,
        "FAMILY_AI_WEB_SEARCH_TOOL_TYPE": payload.web_search_tool_type,
        "FAMILY_AI_IMAGE_SEARCH_PROVIDER": payload.image_search_provider,
        "FAMILY_AI_IMAGE_SEARCH_TIMEOUT_SECONDS": str(payload.image_search_timeout_seconds),
        "FAMILY_AI_VISION_PROVIDER": payload.vision_provider,
        "FAMILY_AI_VISION_BASE_URL": (payload.vision_base_url or "").strip(),
        "FAMILY_AI_VISION_MODEL": payload.vision_model.strip(),
        "FAMILY_AI_VISION_MAX_IMAGE_BYTES": str(payload.vision_max_image_bytes),
        "FAMILY_AI_MUSIC_RECOGNITION_PROVIDER": payload.music_recognition_provider,
        "FAMILY_AI_ACRCLOUD_HOST": (payload.acrcloud_host or "").strip(),
        "FAMILY_AI_MUSIC_RECOGNITION_TIMEOUT_SECONDS": str(
            payload.music_recognition_timeout_seconds
        ),
    }

    if payload.openai_api_key and payload.openai_api_key.strip():
        updates["FAMILY_AI_OPENAI_API_KEY"] = payload.openai_api_key.strip()
    if payload.clear_vision_api_key:
        updates["FAMILY_AI_VISION_API_KEY"] = ""
    elif payload.vision_api_key and payload.vision_api_key.strip():
        updates["FAMILY_AI_VISION_API_KEY"] = payload.vision_api_key.strip()
    if payload.speech_api_key and payload.speech_api_key.strip():
        updates["FAMILY_AI_SPEECH_API_KEY"] = payload.speech_api_key.strip()
    if payload.clear_stt_api_key:
        updates["FAMILY_AI_STT_API_KEY"] = ""
    elif payload.stt_api_key and payload.stt_api_key.strip():
        updates["FAMILY_AI_STT_API_KEY"] = payload.stt_api_key.strip()
    if payload.clear_tts_api_key:
        updates["FAMILY_AI_TTS_API_KEY"] = ""
    elif payload.tts_api_key and payload.tts_api_key.strip():
        updates["FAMILY_AI_TTS_API_KEY"] = payload.tts_api_key.strip()
    if payload.acrcloud_access_key and payload.acrcloud_access_key.strip():
        updates["FAMILY_AI_ACRCLOUD_ACCESS_KEY"] = payload.acrcloud_access_key.strip()
    if payload.acrcloud_access_secret and payload.acrcloud_access_secret.strip():
        updates["FAMILY_AI_ACRCLOUD_ACCESS_SECRET"] = payload.acrcloud_access_secret.strip()
    return updates


def _clear_settings_cache() -> None:
    cache_clear = getattr(get_settings, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


def _configuration_http_error(exc: RuntimeError) -> HTTPException:
    if isinstance(exc, ConfigurationRevisionNotFoundError):
        return HTTPException(status_code=404, detail="Configuration revision not found")
    if isinstance(exc, ConfigurationValidationError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(
        status_code=503,
        detail="Gateway configuration could not be applied safely",
    )


@app.post("/api/settings/preview", response_model=ConfigurationPreviewResponse)
def preview_runtime_settings(
    payload: SettingsUpdateRequest,
    _user: str = Depends(_verify_admin),
    service: GatewayConfigurationService = Depends(get_gateway_configuration_service),
) -> ConfigurationPreviewResponse:
    try:
        changes = service.preview(_settings_updates(payload))
    except ConfigurationValidationError as exc:
        raise _configuration_http_error(exc) from exc
    return ConfigurationPreviewResponse(changes=changes)


@app.get("/api/settings/revisions", response_model=ConfigurationRevisionCollection)
def list_runtime_setting_revisions(
    _user: str = Depends(_verify_admin),
    service: GatewayConfigurationService = Depends(get_gateway_configuration_service),
) -> ConfigurationRevisionCollection:
    return ConfigurationRevisionCollection(items=service.list_revisions())


@app.post(
    "/api/settings/revisions/{revision_id}/rollback",
    response_model=ConfigurationRollbackResponse,
)
def rollback_runtime_settings(
    revision_id: str,
    user: str = Depends(_verify_admin),
    service: GatewayConfigurationService = Depends(get_gateway_configuration_service),
) -> ConfigurationRollbackResponse:
    try:
        revision = service.rollback(revision_id, actor=user)
    except (
        ConfigurationApplyError,
        ConfigurationRevisionNotFoundError,
        ConfigurationValidationError,
    ) as exc:
        raise _configuration_http_error(exc) from exc
    _clear_settings_cache()
    return ConfigurationRollbackResponse(revision=revision)


@app.post("/api/settings", response_model=SettingsResponse)
def update_runtime_settings(
    payload: SettingsUpdateRequest,
    user: str = Depends(_verify_admin),
    service: GatewayConfigurationService = Depends(get_gateway_configuration_service),
) -> SettingsResponse:
    try:
        service.apply(_settings_updates(payload), actor=user)
    except (ConfigurationApplyError, ConfigurationValidationError) as exc:
        raise _configuration_http_error(exc) from exc

    _clear_settings_cache()
    return _settings_response(get_settings())


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

    _clear_settings_cache()
    return {"status": "ok"}


@app.get("/api/healthz")
def healthz() -> dict[str, Any]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("gateway.admin.main:app", host="0.0.0.0", port=8001)
