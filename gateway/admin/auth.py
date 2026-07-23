"""Shared authentication and short-lived admin browser sessions."""

import base64
import hashlib
import hmac
import secrets
import time

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from gateway.app.config import get_settings

security = HTTPBasic(auto_error=False)
SESSION_COOKIE = "family_ai_admin_session"


def verify_admin(
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> str:
    settings = get_settings()
    expected_username = settings.admin_username
    expected_password = settings.admin_password.get_secret_value()

    if credentials is not None:
        valid_username = secrets.compare_digest(credentials.username, expected_username)
        valid_password = secrets.compare_digest(credentials.password, expected_password)
        if valid_username and valid_password:
            return credentials.username

    token = request.cookies.get(SESSION_COOKIE, "")
    if _is_valid_session(
        token,
        username=expected_username,
        password=expected_password,
        ttl_seconds=settings.admin_session_ttl_hours * 3600,
    ):
        return expected_username

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid admin credentials",
        headers={"WWW-Authenticate": "Basic"},
    )


def create_session_token(username: str, password: str, issued_at: int | None = None) -> str:
    """Create a signed token containing no password or reusable Basic credentials."""

    timestamp = issued_at if issued_at is not None else int(time.time())
    payload = f"{username}:{timestamp}"
    signature = hmac.new(
        password.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{timestamp}.{encoded_signature}"


def _is_valid_session(
    token: str,
    *,
    username: str,
    password: str,
    ttl_seconds: int,
) -> bool:
    try:
        timestamp_text, _signature = token.split(".", maxsplit=1)
        timestamp = int(timestamp_text)
    except (TypeError, ValueError):
        return False
    now = int(time.time())
    if timestamp > now + 60 or now - timestamp > ttl_seconds:
        return False
    expected = create_session_token(username, password, issued_at=timestamp)
    return secrets.compare_digest(token, expected)
