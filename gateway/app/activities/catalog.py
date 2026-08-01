"""Load the versioned activity catalog without executable scenario code."""

import json
from pathlib import Path

from gateway.app.activities.schemas import (
    ActivityCatalogDocument,
    ActivityDefinition,
)


class ActivityNotFoundError(LookupError):
    """Requested configured activity does not exist."""


class ActivityCatalog:
    def __init__(self, path: Path | None = None) -> None:
        catalog_path = path or Path(__file__).with_name("catalog.json")
        document = ActivityCatalogDocument.model_validate(
            json.loads(catalog_path.read_text(encoding="utf-8"))
        )
        self.schema_version = document.schema_version
        self._items = {item.id: item for item in document.activities}

    def list(self, *, agent_id: str | None = None) -> tuple[ActivityDefinition, ...]:
        items = self._items.values()
        if agent_id is not None:
            items = (item for item in items if item.agent_id == agent_id)
        return tuple(items)

    def get(self, activity_id: str) -> ActivityDefinition:
        try:
            return self._items[activity_id]
        except KeyError as exc:
            raise ActivityNotFoundError("Activity is unavailable") from exc
