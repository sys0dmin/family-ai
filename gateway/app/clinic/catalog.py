"""Versioned pretend-clinic case catalog."""

from pathlib import Path

from gateway.app.clinic.schemas import ClinicCase, ClinicCatalogDocument


class ClinicCaseNotFoundError(LookupError):
    """Requested clinic case is not available."""


class ClinicCaseCatalog:
    def __init__(
        self,
        path: Path | None = None,
        overlays: dict[str, dict[str, str]] | None = None,
        custom_cases: tuple[ClinicCase, ...] = (),
    ) -> None:
        catalog_path = path or Path(__file__).with_name("catalog.json")
        document = ClinicCatalogDocument.model_validate_json(
            catalog_path.read_text(encoding="utf-8")
        )
        self._schema_version = document.schema_version
        allowed_fields = {
            "title",
            "short_title",
            "description",
            "patient_name",
            "patient_icon",
            "mood",
            "complaint",
            "opening_text",
            "completion_text",
        }
        self._builtin_ids = frozenset(item.id for item in document.cases)
        self._items = {
            item.id: item.model_copy(
                update={
                    key: value
                    for key, value in (overlays or {}).get(item.id, {}).items()
                    if key in allowed_fields
                }
            )
            for item in document.cases
        }
        for item in custom_cases:
            self._items[item.id] = item

    @property
    def schema_version(self) -> int:
        return self._schema_version

    def list(self) -> tuple[ClinicCase, ...]:
        return tuple(self._items.values())

    def get(self, case_id: str) -> ClinicCase:
        try:
            return self._items[case_id]
        except KeyError as exc:
            raise ClinicCaseNotFoundError(case_id) from exc

    def is_builtin(self, case_id: str) -> bool:
        """Return whether a case comes from the checked-in safety catalog."""

        return case_id in self._builtin_ids
