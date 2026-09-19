"""Versioned, parent-authored clinic scenarios with fixed safety mechanics."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gateway.app.clinic import ClinicCaseCatalog
from gateway.app.clinic.schemas import ClinicCase
from gateway.app.models.clinic_scenario_draft import ClinicScenarioDraft

EDITABLE_FIELDS = frozenset(
    {
        "title",
        "short_title",
        "description",
        "patient_name",
        "patient_icon",
        "mood",
        "complaint",
        "opening_text",
        "completion_text",
        "color",
    }
)
_CUSTOM_KIND = "custom_case"


@dataclass(frozen=True)
class PublishedClinicCatalog:
    """Published parent customizations, split by their safe runtime role."""

    overlays: dict[str, dict[str, str]]
    custom_cases: tuple[ClinicCase, ...]


def published_clinic_catalog(session: Session) -> PublishedClinicCatalog:
    """Load published drafts without letting parent data change procedures."""

    overlays: dict[str, dict[str, str]] = {}
    custom_cases: list[ClinicCase] = []
    rows = session.scalars(
        select(ClinicScenarioDraft).where(ClinicScenarioDraft.status == "published")
    ).all()
    for row in rows:
        payload = row.payload
        if payload.get("kind") == _CUSTOM_KIND:
            custom_cases.append(ClinicCase.model_validate(payload["case"]))
            continue
        overlays[row.case_id] = {
            key: value
            for key, value in payload.items()
            if key in EDITABLE_FIELDS and isinstance(value, str)
        }
    return PublishedClinicCatalog(overlays=overlays, custom_cases=tuple(custom_cases))


class ClinicDraftService:
    """Create and publish parent drafts while retaining verified mechanics."""

    def __init__(self, session: Session, catalog: ClinicCaseCatalog) -> None:
        self._session = session
        self._catalog = catalog

    def create(
        self, case_id: str, payload: dict[str, str], created_by: str = "admin"
    ) -> ClinicScenarioDraft:
        base = self._catalog.get(case_id)
        clean = self._clean(payload)
        updated = ClinicCase.model_validate({**base.model_dump(), **clean})
        stored: dict[str, object] = clean
        if not self._catalog.is_builtin(case_id):
            stored = {"kind": _CUSTOM_KIND, "case": updated.model_dump(mode="json")}
        return self._new_draft(case_id, stored, created_by)

    def create_custom(
        self,
        template_case_id: str,
        payload: dict[str, str],
        created_by: str = "admin",
    ) -> ClinicScenarioDraft:
        """Clone a safe template and replace only the patient-facing story."""

        template = self._catalog.get(template_case_id)
        clean = self._clean(payload)
        patient_name = clean.get("patient_name")
        if not patient_name:
            raise ValueError("Patient name is required")
        complaint = clean.get("complaint", template.complaint)
        title = clean.get("title", f"Забота о {patient_name}")
        changes = {
            "id": f"parent_{uuid.uuid4().hex[:10]}",
            "version": 1,
            "title": title,
            "short_title": clean.get("short_title", title[:30]),
            "description": clean.get("description", complaint),
            "patient_name": patient_name,
            "patient_icon": clean.get("patient_icon", template.patient_icon),
            "mood": clean.get("mood", template.mood),
            "complaint": complaint,
            "opening_text": clean.get(
                "opening_text",
                (
                    f"{patient_name} пришёл в палату. Давай спокойно "
                    "поздороваемся и позаботимся о нём."
                ),
            ),
            "completion_text": clean.get(
                "completion_text",
                f"{patient_name} улыбается и благодарит тебя за внимательную заботу.",
            ),
            "color": clean.get("color", template.color),
        }
        custom_case = ClinicCase.model_validate({**template.model_dump(), **changes})
        return self._new_draft(
            custom_case.id,
            {"kind": _CUSTOM_KIND, "case": custom_case.model_dump(mode="json")},
            created_by,
        )

    def publish(self, draft_id: uuid.UUID) -> ClinicScenarioDraft:
        draft = self._session.get(ClinicScenarioDraft, draft_id)
        if draft is None:
            raise LookupError("Clinic draft not found")
        for row in self._session.scalars(
            select(ClinicScenarioDraft).where(
                ClinicScenarioDraft.case_id == draft.case_id,
                ClinicScenarioDraft.status == "published",
            )
        ):
            row.status = "superseded"
        draft.status = "published"
        draft.published_at = datetime.now(UTC)
        self._session.flush()
        return draft

    def _new_draft(
        self, case_id: str, payload: dict[str, object], created_by: str
    ) -> ClinicScenarioDraft:
        version = (
            self._session.scalar(
                select(func.max(ClinicScenarioDraft.version)).where(
                    ClinicScenarioDraft.case_id == case_id
                )
            )
            or 0
        ) + 1
        draft = ClinicScenarioDraft(
            id=uuid.uuid4(),
            case_id=case_id,
            version=version,
            status="draft",
            payload=payload,
            created_by=created_by,
        )
        self._session.add(draft)
        self._session.flush()
        return draft

    @staticmethod
    def _clean(payload: dict[str, str]) -> dict[str, str]:
        return {
            key: value.strip()
            for key, value in payload.items()
            if key in EDITABLE_FIELDS and isinstance(value, str) and value.strip()
        }
