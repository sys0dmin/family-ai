"""Select, persist, and safely proxy visual message attachments."""

import logging
import re
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from gateway.app.agents import ActiveAgent
from gateway.app.images import ImageSearchProvider
from gateway.app.models import Message, MessageMedia

logger = logging.getLogger(__name__)

VISUAL_INTENT_PATTERN = re.compile(
    r"\b(?:покажи|фото|картин\w*|как\s+выгляд\w*|что\s+такое|"
    r"кто\s+такой|кто\s+такая|расскажи\s+про|из\s+чего\s+состоит)\b",
    re.IGNORECASE,
)
OUTDOOR_IDENTIFICATION_PATTERN = re.compile(
    r"(?:можно\s+.*есть|съедоб\w*|определи\w*|что\s+за\s+(?:гриб|ягод|растен))",
    re.IGNORECASE,
)
QUERY_CATALOG = (
    (re.compile(r"фри.?кул|free.?cool", re.IGNORECASE), "data center free cooling equipment"),
    (
        re.compile(r"\bцод\b|дата.?центр|центр обработки данных", re.IGNORECASE),
        "data center server racks",
    ),
    (re.compile(r"серверн\w*\s+стойк|стойк\w*\s+сервер", re.IGNORECASE), "server rack data center"),
    (re.compile(r"\bсервер\w*\b", re.IGNORECASE), "computer server rack"),
    (re.compile(r"процессор|\bcpu\b", re.IGNORECASE), "computer CPU processor close up"),
    (re.compile(r"оперативн\w*\s+памят|\bram\b", re.IGNORECASE), "computer RAM memory module"),
    (re.compile(r"кул+ер|вентилятор", re.IGNORECASE), "computer cooling fan cooler"),
    (re.compile(r"материнск\w*\s+плат", re.IGNORECASE), "computer motherboard close up"),
    (
        re.compile(r"ж[её]стк\w*\s+диск|\bhdd\b|\bssd\b", re.IGNORECASE),
        "computer storage drive SSD HDD",
    ),
    (re.compile(r"лиса|лисиц", re.IGNORECASE), "red fox wildlife"),
    (re.compile(r"медвед", re.IGNORECASE), "brown bear wildlife"),
    (re.compile(r"волк", re.IGNORECASE), "gray wolf wildlife"),
    (re.compile(r"клещ", re.IGNORECASE), "tick macro wildlife"),
    (re.compile(r"багульник", re.IGNORECASE), "Rhododendron tomentosum plant"),
)
AGENT_QUERY_PREFIX = {
    "tech_guide": "computer technology",
    "outdoor_guide": "nature wildlife outdoor",
    "scientist": "science educational",
    "teacher_friend": "educational",
}
STOP_WORDS = {
    "байтик",
    "мурка",
    "лера",
    "лерочка",
    "папа",
    "мама",
    "пожалуйста",
    "можешь",
    "мне",
    "это",
    "такое",
    "про",
    "расскажи",
    "покажи",
    "что",
    "кто",
    "как",
    "выглядит",
}
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class ProxiedImage:
    content: bytes
    content_type: str


class VisualMediaService:
    """Application-level visual capability independent from an image vendor."""

    def __init__(
        self,
        session: Session,
        provider: ImageSearchProvider | None,
        timeout_seconds: float = 6.0,
    ) -> None:
        self._session = session
        self._provider = provider
        self._timeout_seconds = timeout_seconds

    async def attach_for_turn(
        self,
        message: Message,
        agent: ActiveAgent,
        child_text: str,
    ) -> None:
        """Attach at most one relevant image when the agent and request allow it."""

        if self._provider is None or "image_search" not in agent.tools:
            return
        if not VISUAL_INTENT_PATTERN.search(child_text):
            return
        if agent.id == "outdoor_guide" and OUTDOOR_IDENTIFICATION_PATTERN.search(child_text):
            return
        query = self._build_query(child_text, agent.id)
        if not query:
            return
        try:
            result = await self._provider.search(query)
        except (httpx.HTTPError, ValueError, KeyError):
            logger.exception("image_search_failed", extra={"agent_id": agent.id})
            return
        if result is None:
            return
        media = MessageMedia(
            id=uuid.uuid4(),
            message_id=message.id,
            media_type="image",
            remote_url=result.remote_url,
            source_url=result.source_url,
            title=result.title,
            creator=result.creator,
            license_name=result.license_name,
            license_url=result.license_url,
        )
        self._session.add(media)
        self._session.flush()

    async def fetch_image(self, media_id: uuid.UUID) -> ProxiedImage | None:
        """Fetch a stored Openverse thumbnail without exposing its URL to the child UI."""

        media = self._session.get(MessageMedia, media_id)
        if media is None or media.media_type != "image":
            return None
        parsed = urlparse(media.remote_url)
        if parsed.scheme != "https" or parsed.hostname != "api.openverse.org":
            logger.warning("blocked_untrusted_media_url", extra={"media_id": str(media_id)})
            return None
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "FamilyAI/0.1 (home educational project)"},
        ) as client:
            response = await client.get(media.remote_url)
            response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";", maxsplit=1)[0]
        if content_type not in ALLOWED_IMAGE_TYPES or len(response.content) > MAX_IMAGE_BYTES:
            return None
        return ProxiedImage(content=response.content, content_type=content_type)

    @staticmethod
    def _build_query(child_text: str, agent_id: str) -> str:
        for pattern, query in QUERY_CATALOG:
            if pattern.search(child_text):
                return query
        words = re.findall(r"[a-zа-яё]{3,}", child_text.lower())
        safe_words = [word for word in words if word not in STOP_WORDS][:8]
        if not safe_words:
            return ""
        prefix = AGENT_QUERY_PREFIX.get(agent_id, "educational")
        return f"{prefix} {' '.join(safe_words)}"[:160]
