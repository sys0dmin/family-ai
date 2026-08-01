"""Validated provider-neutral activity configuration."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ActivityStep(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$", max_length=50)
    icon: str = Field(min_length=1, max_length=8)
    title: str = Field(min_length=1, max_length=80)
    instruction: str = Field(min_length=20, max_length=1200)


class ActivityDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$", max_length=50)
    version: int = Field(ge=1)
    agent_id: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=2, max_length=100)
    short_title: str = Field(min_length=1, max_length=30)
    description: str = Field(min_length=5, max_length=240)
    icon: str = Field(min_length=1, max_length=8)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    opening_text: str = Field(min_length=20, max_length=1200)
    completion_summary: str = Field(min_length=20, max_length=600)
    steps: tuple[ActivityStep, ...] = Field(min_length=2, max_length=6)

    @model_validator(mode="after")
    def ensure_unique_steps(self) -> "ActivityDefinition":
        identifiers = [step.id for step in self.steps]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Activity step ids must be unique")
        return self


class ActivityCatalogDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = Field(ge=1)
    activities: tuple[ActivityDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def ensure_unique_activities(self) -> "ActivityCatalogDocument":
        identifiers = [activity.id for activity in self.activities]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Activity ids must be unique")
        return self
