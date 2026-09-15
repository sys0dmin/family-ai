"""Validated provider-neutral pretend-clinic configuration."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

IDENTIFIER_PATTERN = r"^[a-z0-9_]+$"


class ClinicVital(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=IDENTIFIER_PATTERN, max_length=40)
    icon: str = Field(min_length=1, max_length=8)
    label: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=20)
    unit: str = Field(default="", max_length=12)
    state: str = Field(pattern=r"^(calm|attention|good)$")
    readings: tuple["ClinicVitalReading", ...] = Field(default=(), max_length=8)


class ClinicVitalReading(BaseModel):
    """One plausible simulated monitor reading for a fictional patient."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str = Field(min_length=1, max_length=20)
    state: str = Field(pattern=r"^(calm|attention|good)$")


class ClinicVitalUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    vital_id: str = Field(pattern=IDENTIFIER_PATTERN, max_length=40)
    value: str = Field(min_length=1, max_length=20)
    state: str = Field(pattern=r"^(calm|attention|good)$")


class ClinicAction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=IDENTIFIER_PATTERN, max_length=50)
    icon: str = Field(min_length=1, max_length=8)
    label: str = Field(min_length=1, max_length=50)
    response: str = Field(min_length=10, max_length=300)
    updates: tuple[ClinicVitalUpdate, ...] = Field(default=())


class ClinicCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=IDENTIFIER_PATTERN, max_length=50)
    version: int = Field(ge=1)
    title: str = Field(min_length=2, max_length=80)
    short_title: str = Field(min_length=1, max_length=30)
    description: str = Field(min_length=5, max_length=200)
    patient_name: str = Field(min_length=1, max_length=40)
    patient_icon: str = Field(min_length=1, max_length=8)
    mood: str = Field(default="спокойное", min_length=1, max_length=80)
    complaint: str = Field(default="Хочет, чтобы о нём позаботились.", min_length=1, max_length=160)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    opening_text: str = Field(min_length=20, max_length=500)
    completion_text: str = Field(min_length=20, max_length=400)
    vitals: tuple[ClinicVital, ...] = Field(min_length=1, max_length=6)
    actions: tuple[ClinicAction, ...] = Field(min_length=1, max_length=8)
    required_action_ids: tuple[str, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_references(self) -> "ClinicCase":
        vital_ids = [item.id for item in self.vitals]
        action_ids = [item.id for item in self.actions]
        if len(vital_ids) != len(set(vital_ids)):
            raise ValueError("Clinic vital ids must be unique")
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("Clinic action ids must be unique")
        if not set(self.required_action_ids).issubset(action_ids):
            raise ValueError("Required clinic actions must exist")
        if any(
            update.vital_id not in vital_ids for action in self.actions for update in action.updates
        ):
            raise ValueError("Clinic action references an unknown vital")
        return self


class ClinicCatalogDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = Field(ge=1)
    cases: tuple[ClinicCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def ensure_unique_cases(self) -> "ClinicCatalogDocument":
        identifiers = [item.id for item in self.cases]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Clinic case ids must be unique")
        return self
