"""Safe preview, revision, and apply lifecycle for Gateway configuration."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from gateway.admin.auth import verify_admin
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
)
from gateway.admin.session_router import clear_settings_cache, must_change_password
from gateway.admin.settings_schemas import SettingsResponse, SettingsUpdateRequest
from gateway.app.config import get_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


def get_gateway_configuration_service() -> GatewayConfigurationService:
    settings = get_settings()
    return GatewayConfigurationService(
        env_path=Path(settings.admin_env_file),
        history_dir=Path(settings.admin_config_history_dir),
        settings=settings,
    )


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def settings_response(settings: Any) -> SettingsResponse:
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
        voice_max_in_flight=settings.voice_max_in_flight,
        voice_stt_timeout_seconds=settings.voice_stt_timeout_seconds,
        voice_llm_timeout_seconds=settings.voice_llm_timeout_seconds,
        voice_tts_timeout_seconds=settings.voice_tts_timeout_seconds,
        must_change_password=must_change_password(settings),
    )


def _set_optional_secret(
    updates: dict[str, str],
    environment_key: str,
    value: str | None,
    *,
    clear: bool = False,
) -> None:
    if clear:
        updates[environment_key] = ""
    elif value and value.strip():
        updates[environment_key] = value.strip()


def settings_updates(payload: SettingsUpdateRequest) -> dict[str, str]:
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
        "FAMILY_AI_VOICE_MAX_IN_FLIGHT": str(payload.voice_max_in_flight),
        "FAMILY_AI_VOICE_STT_TIMEOUT_SECONDS": str(payload.voice_stt_timeout_seconds),
        "FAMILY_AI_VOICE_LLM_TIMEOUT_SECONDS": str(payload.voice_llm_timeout_seconds),
        "FAMILY_AI_VOICE_TTS_TIMEOUT_SECONDS": str(payload.voice_tts_timeout_seconds),
    }
    _set_optional_secret(updates, "FAMILY_AI_OPENAI_API_KEY", payload.openai_api_key)
    _set_optional_secret(updates, "FAMILY_AI_SPEECH_API_KEY", payload.speech_api_key)
    _set_optional_secret(
        updates,
        "FAMILY_AI_VISION_API_KEY",
        payload.vision_api_key,
        clear=payload.clear_vision_api_key,
    )
    _set_optional_secret(
        updates,
        "FAMILY_AI_STT_API_KEY",
        payload.stt_api_key,
        clear=payload.clear_stt_api_key,
    )
    _set_optional_secret(
        updates,
        "FAMILY_AI_TTS_API_KEY",
        payload.tts_api_key,
        clear=payload.clear_tts_api_key,
    )
    _set_optional_secret(
        updates,
        "FAMILY_AI_ACRCLOUD_ACCESS_KEY",
        payload.acrcloud_access_key,
    )
    _set_optional_secret(
        updates,
        "FAMILY_AI_ACRCLOUD_ACCESS_SECRET",
        payload.acrcloud_access_secret,
    )
    return updates


def _configuration_http_error(exc: RuntimeError) -> HTTPException:
    if isinstance(exc, ConfigurationRevisionNotFoundError):
        return HTTPException(status_code=404, detail="Configuration revision not found")
    if isinstance(exc, ConfigurationValidationError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(
        status_code=503,
        detail="Gateway configuration could not be applied safely",
    )


@router.get("", response_model=SettingsResponse)
def get_runtime_settings(_user: str = Depends(verify_admin)) -> SettingsResponse:
    return settings_response(get_settings())


@router.post("/preview", response_model=ConfigurationPreviewResponse)
def preview_runtime_settings(
    payload: SettingsUpdateRequest,
    _user: str = Depends(verify_admin),
    service: GatewayConfigurationService = Depends(get_gateway_configuration_service),
) -> ConfigurationPreviewResponse:
    try:
        changes = service.preview(settings_updates(payload))
    except ConfigurationValidationError as exc:
        raise _configuration_http_error(exc) from exc
    return ConfigurationPreviewResponse(changes=changes)


@router.get("/revisions", response_model=ConfigurationRevisionCollection)
def list_runtime_setting_revisions(
    _user: str = Depends(verify_admin),
    service: GatewayConfigurationService = Depends(get_gateway_configuration_service),
) -> ConfigurationRevisionCollection:
    return ConfigurationRevisionCollection(items=service.list_revisions())


@router.post(
    "/revisions/{revision_id}/rollback",
    response_model=ConfigurationRollbackResponse,
)
def rollback_runtime_settings(
    revision_id: str,
    user: str = Depends(verify_admin),
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
    clear_settings_cache()
    return ConfigurationRollbackResponse(revision=revision)


@router.post("", response_model=SettingsResponse)
def update_runtime_settings(
    payload: SettingsUpdateRequest,
    user: str = Depends(verify_admin),
    service: GatewayConfigurationService = Depends(get_gateway_configuration_service),
) -> SettingsResponse:
    try:
        service.apply(settings_updates(payload), actor=user)
    except (ConfigurationApplyError, ConfigurationValidationError) as exc:
        raise _configuration_http_error(exc) from exc
    clear_settings_cache()
    return settings_response(get_settings())
