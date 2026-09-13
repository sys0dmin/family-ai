"""Protected contracts for pretend-clinic preview and operations."""

from pydantic import BaseModel

from gateway.app.clinic.schemas import ClinicCase
from gateway.app.schemas.clinic import ClinicSessionResponse


class ClinicAdminCatalogResponse(BaseModel):
    schema_version: int
    items: list[ClinicCase]


class ClinicAdminSessionsResponse(BaseModel):
    items: list[ClinicSessionResponse]
