"""Public, secret-free contracts for managed Gateway configuration revisions."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ConfigurationChange(BaseModel):
    key: str
    before: str
    after: str
    secret: bool = False


class ConfigurationPreviewResponse(BaseModel):
    valid: bool = True
    changes: list[ConfigurationChange]


class ConfigurationRevisionResponse(BaseModel):
    id: str
    created_at: datetime
    actor: str
    operation: Literal["baseline", "apply", "rollback"]
    status: Literal["active", "superseded", "rolled_back"]
    fingerprint: str
    source_revision_id: str | None = None
    changes: list[ConfigurationChange]


class ConfigurationRevisionCollection(BaseModel):
    items: list[ConfigurationRevisionResponse]


class ConfigurationRollbackResponse(BaseModel):
    status: Literal["applied"] = "applied"
    revision: ConfigurationRevisionResponse
