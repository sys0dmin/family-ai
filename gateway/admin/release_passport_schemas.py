"""Validated contracts for the runtime release passport."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

PassportStatus = Literal["aligned", "drift", "unavailable"]


class ComponentReleaseIdentity(BaseModel):
    component: Literal["gateway", "speech"]
    status: PassportStatus
    app_version: str | None = None
    actual_commit: str | None = None
    expected_commit: str | None = None
    uptime_seconds: float | None = None


class DatabaseReleaseIdentity(BaseModel):
    status: PassportStatus
    current_revision: str | None = None
    code_head: str | None = None


class AndroidReleaseIdentity(BaseModel):
    status: Literal["observed", "unavailable"]
    version: str | None = None
    source_commit: str | None = None
    observed_at: datetime | None = None


class ConfigurationIdentity(BaseModel):
    status: PassportStatus
    fingerprint: str | None = None


class ReleasePassportResponse(BaseModel):
    status: PassportStatus
    checked_at: datetime
    gateway: ComponentReleaseIdentity
    speech: ComponentReleaseIdentity
    database: DatabaseReleaseIdentity
    android: AndroidReleaseIdentity
    configuration: ConfigurationIdentity
