"""Versioned pretend-clinic case catalog."""

from pathlib import Path

from gateway.app.clinic.schemas import ClinicCase, ClinicCatalogDocument


class ClinicCaseNotFoundError(LookupError):
    """Requested clinic case is not available."""


class ClinicCaseCatalog:
    def __init__(self, path: Path | None = None) -> None:
        catalog_path = path or Path(__file__).with_name("catalog.json")
        document = ClinicCatalogDocument.model_validate_json(
            catalog_path.read_text(encoding="utf-8")
        )
        self._schema_version = document.schema_version
        self._items = {item.id: item for item in document.cases}

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
