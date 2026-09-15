"""Versioned parent drafts for the clinic catalog."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gateway.app.models.clinic_scenario_draft import ClinicScenarioDraft
from gateway.app.clinic import ClinicCaseCatalog
from gateway.app.clinic.schemas import ClinicCase

EDITABLE_FIELDS = {
    "title", "short_title", "description", "patient_name", "patient_icon",
    "mood", "complaint", "opening_text", "completion_text",
}


def published_clinic_overlays(session: Session) -> dict[str, dict[str, str]]:
    rows = session.scalars(select(ClinicScenarioDraft).where(ClinicScenarioDraft.status == "published")).all()
    return {row.case_id: row.payload for row in rows}


class ClinicDraftService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, case_id: str, payload: dict[str, str], created_by: str = "admin") -> ClinicScenarioDraft:
        clean = {key: value.strip() for key, value in payload.items() if key in EDITABLE_FIELDS and isinstance(value, str) and value.strip()}
        base = ClinicCaseCatalog().get(case_id)
        ClinicCase.model_validate({**base.model_dump(), **clean})
        version = (self._session.scalar(select(func.max(ClinicScenarioDraft.version)).where(ClinicScenarioDraft.case_id == case_id)) or 0) + 1
        draft = ClinicScenarioDraft(id=uuid.uuid4(), case_id=case_id, version=version, status="draft", payload=clean, created_by=created_by)
        self._session.add(draft)
        self._session.flush()
        return draft

    def publish(self, draft_id: uuid.UUID) -> ClinicScenarioDraft:
        draft = self._session.get(ClinicScenarioDraft, draft_id)
        if draft is None: raise LookupError("Clinic draft not found")
        for row in self._session.scalars(select(ClinicScenarioDraft).where(ClinicScenarioDraft.case_id == draft.case_id, ClinicScenarioDraft.status == "published")):
            row.status = "superseded"
        draft.status = "published"
        draft.published_at = datetime.now(UTC)
        self._session.flush()
        return draft
