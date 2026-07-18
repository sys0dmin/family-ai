"""Visual search provider abstraction."""

from gateway.app.images.base import ImageSearchProvider
from gateway.app.images.openverse import OpenverseImageSearchProvider
from gateway.app.images.schemas import ImageSearchResult

__all__ = ["ImageSearchProvider", "ImageSearchResult", "OpenverseImageSearchProvider"]

