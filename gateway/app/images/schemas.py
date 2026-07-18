"""Provider-independent image search values."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ImageSearchResult:
    """One reusable image with attribution metadata."""

    remote_url: str
    source_url: str
    title: str
    creator: str | None
    license_name: str
    license_url: str | None

