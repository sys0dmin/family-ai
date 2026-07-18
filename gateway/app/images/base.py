"""Replaceable provider interface for visual search."""

from abc import ABC, abstractmethod

from gateway.app.images.schemas import ImageSearchResult


class ImageSearchProvider(ABC):
    """Find child-safe, reusable visual material."""

    @abstractmethod
    async def search(self, query: str) -> ImageSearchResult | None:
        raise NotImplementedError

