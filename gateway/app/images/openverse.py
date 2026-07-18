"""Openverse implementation of child-safe image search."""

from urllib.parse import urlparse

import httpx

from gateway.app.images.base import ImageSearchProvider
from gateway.app.images.schemas import ImageSearchResult


class OpenverseImageSearchProvider(ImageSearchProvider):
    """Search openly licensed images with sensitive results disabled."""

    API_URL = "https://api.openverse.org/v1/images/"

    def __init__(self, timeout_seconds: float = 6.0) -> None:
        self._timeout_seconds = timeout_seconds

    async def search(self, query: str) -> ImageSearchResult | None:
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds,
            headers={"User-Agent": "FamilyAI/0.1 (home educational project)"},
        ) as client:
            response = await client.get(
                self.API_URL,
                params={
                    "q": query,
                    "page_size": 5,
                    "mature": "false",
                },
            )
            response.raise_for_status()

        for item in response.json().get("results", []):
            result = self._normalize(item)
            if result is not None:
                return result
        return None

    @staticmethod
    def _normalize(item: dict[str, object]) -> ImageSearchResult | None:
        if item.get("mature") is not False or item.get("sensitivity"):
            return None
        thumbnail = str(item.get("thumbnail") or "")
        source_url = str(item.get("foreign_landing_url") or item.get("detail_url") or "")
        if not _is_https_url(thumbnail, required_host="api.openverse.org"):
            return None
        if not _is_https_url(source_url):
            return None
        license_name = str(item.get("license") or "").upper()
        if not license_name:
            return None
        creator = str(item.get("creator") or "").strip() or None
        license_url = str(item.get("license_url") or "").strip() or None
        if license_url is not None and not _is_https_url(license_url):
            license_url = None
        return ImageSearchResult(
            remote_url=thumbnail,
            source_url=source_url,
            title=str(item.get("title") or "Иллюстрация").strip()[:300],
            creator=creator[:200] if creator else None,
            license_name=license_name[:50],
            license_url=license_url,
        )


def _is_https_url(value: str, required_host: str | None = None) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and (
        required_host is None or parsed.hostname == required_host
    )

