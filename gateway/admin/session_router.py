"""Browser-session and parent credential lifecycle routes."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from gateway.admin.auth import SESSION_COOKIE, create_session_token, verify_admin
from gateway.admin.environment_file import upsert_env_values
from gateway.app.config import get_settings

router = APIRouter(tags=["admin session"])


class ChangePasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=200)

    @field_validator("new_password")
    @classmethod
    def reject_multiline_password(cls, value: str) -> str:
        if any(character in value for character in "\r\n\0"):
            raise ValueError("password must be single-line")
        return value


def must_change_password(settings: Any) -> bool:
    current_password = settings.admin_password.get_secret_value()
    return settings.admin_force_password_change or current_password == "change-me"


def clear_settings_cache() -> None:
    cache_clear = getattr(get_settings, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


@router.post("/api/session", status_code=204)
def create_admin_session(
    request: Request,
    response: Response,
    _user: str = Depends(verify_admin),
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


@router.delete("/api/session", status_code=204)
def delete_admin_session(response: Response) -> None:
    """Forget the current browser session."""

    response.delete_cookie(
        key=SESSION_COOKIE,
        httponly=True,
        samesite="strict",
        path="/",
    )


@router.post("/api/change-password")
def change_admin_password(
    payload: ChangePasswordRequest,
    _user: str = Depends(verify_admin),
) -> dict[str, str]:
    new_password = payload.new_password.strip()
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    settings = get_settings()
    upsert_env_values(
        Path(settings.admin_env_file),
        {
            "FAMILY_AI_ADMIN_PASSWORD": new_password,
            "FAMILY_AI_ADMIN_FORCE_PASSWORD_CHANGE": "false",
        },
    )
    clear_settings_cache()
    return {"status": "ok"}
