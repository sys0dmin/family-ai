"""ACRCloud humming and recorded-music recognition adapter."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from gateway.app.music.base import MusicRecognitionProvider
from gateway.app.music.schemas import (
    MusicRecognitionRequest,
    MusicRecognitionResponse,
    RecognizedTrack,
)

MAX_SAMPLE_BYTES = 5 * 1024 * 1024
Transport = Callable[[Request, float], dict[str, Any]]


class MusicRecognitionProviderError(RuntimeError):
    """Raised when the external recognizer cannot return a valid response."""


def _send_json(request: Request, timeout_seconds: float) -> dict[str, Any]:
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _multipart_body(
    fields: dict[str, str],
    *,
    filename: str,
    content_type: str,
    content: bytes,
) -> tuple[str, bytes]:
    boundary = f"family-ai-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            ]
        )
    safe_filename = Path(filename).name.replace('"', "")[:100] or "recording.webm"
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            (
                'Content-Disposition: form-data; name="sample"; '
                f'filename="{safe_filename}"\r\n'
            ).encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return boundary, b"".join(chunks)


class AcrCloudMusicRecognitionProvider(MusicRecognitionProvider):
    """Identify humming or recorded music through a signed ACRCloud request."""

    def __init__(
        self,
        *,
        host: str,
        access_key: str,
        access_secret: str,
        timeout_seconds: float = 8.0,
        transport: Transport = _send_json,
    ) -> None:
        parsed = urlparse(host if "://" in host else f"https://{host}")
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not hostname.endswith(".acrcloud.com"):
            raise ValueError("ACRCloud host must be an HTTPS acrcloud.com endpoint")
        self._url = f"https://{hostname}/v1/identify"
        self._access_key = access_key
        self._access_secret = access_secret
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def recognize(
        self,
        request: MusicRecognitionRequest,
    ) -> MusicRecognitionResponse:
        if not request.audio_content or len(request.audio_content) > MAX_SAMPLE_BYTES:
            return MusicRecognitionResponse(matches=())

        timestamp = str(int(time.time()))
        string_to_sign = "\n".join(
            ["POST", "/v1/identify", self._access_key, "audio", "1", timestamp]
        )
        signature = base64.b64encode(
            hmac.new(
                self._access_secret.encode("ascii"),
                string_to_sign.encode("ascii"),
                hashlib.sha1,
            ).digest()
        ).decode("ascii")
        fields = {
            "access_key": self._access_key,
            "sample_bytes": str(len(request.audio_content)),
            "timestamp": timestamp,
            "signature": signature,
            "data_type": "audio",
            "signature_version": "1",
        }
        boundary, body = _multipart_body(
            fields,
            filename=request.filename,
            content_type=request.content_type,
            content=request.audio_content,
        )
        http_request = Request(
            self._url,
            data=body,
            method="POST",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Accept": "application/json",
                "User-Agent": "family-ai-gateway/0.1",
            },
        )
        try:
            payload = await asyncio.to_thread(
                self._transport,
                http_request,
                self._timeout_seconds,
            )
        except Exception as exc:
            raise MusicRecognitionProviderError("Music recognition request failed") from exc

        status = payload.get("status") or {}
        if status.get("code") != 0:
            return MusicRecognitionResponse(matches=())
        metadata = payload.get("metadata") or {}
        raw_matches = [*(metadata.get("humming") or []), *(metadata.get("music") or [])]
        matches: list[RecognizedTrack] = []
        seen: set[tuple[str, str]] = set()
        for item in raw_matches:
            title = str(item.get("title") or "").strip()[:200]
            artists = item.get("artists") or []
            artist = str(artists[0].get("name") or "").strip()[:200] if artists else ""
            if not title or not artist or (title.casefold(), artist.casefold()) in seen:
                continue
            seen.add((title.casefold(), artist.casefold()))
            album = str((item.get("album") or {}).get("name") or "").strip()[:200] or None
            try:
                score = float(item["score"]) if item.get("score") is not None else None
            except (TypeError, ValueError):
                score = None
            matches.append(
                RecognizedTrack(title=title, artist=artist, album=album, score=score)
            )
        matches.sort(key=lambda item: item.score if item.score is not None else -1, reverse=True)
        return MusicRecognitionResponse(matches=tuple(matches[:3]))
