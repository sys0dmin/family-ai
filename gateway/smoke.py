"""Post-deploy functional smoke-test for the Family AI production contour."""

from __future__ import annotations

import argparse
import json
import struct
import sys
import time
import zlib
from collections.abc import Callable
from dataclasses import asdict, dataclass

import httpx

from gateway.app.config import Settings

SMOKE_TEXT = "Проверка связи"
VISION_QUESTION = "Кратко опиши цвет тестового квадрата."


class SmokeStageError(RuntimeError):
    """Describe one failed release stage without leaking response bodies or secrets."""

    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(f"{stage}: {reason}")
        self.stage = stage
        self.reason = reason


@dataclass(frozen=True)
class StageResult:
    name: str
    status: str
    duration_ms: int


class ReleaseSmokeRunner:
    """Exercise public and protected HTTP contracts without persistent user data."""

    def __init__(
        self,
        client: httpx.Client,
        settings: Settings,
        *,
        gateway_url: str,
        admin_url: str,
    ) -> None:
        self._client = client
        self._settings = settings
        self._gateway_url = gateway_url.rstrip("/")
        self._admin_url = admin_url.rstrip("/")
        self._auth = (
            settings.admin_username,
            settings.admin_password.get_secret_value(),
        )
        self._audio: tuple[bytes, str] | None = None

    def run(self) -> list[StageResult]:
        stages: list[tuple[str, Callable[[], str]]] = [
            ("admin_ui", self._check_admin_ui),
            ("gateway_database", self._check_gateway_database),
            ("llm", self._check_llm),
            ("tts", self._check_tts),
            ("stt", self._check_stt),
            ("vision", self._check_vision),
        ]
        results: list[StageResult] = []
        for name, check in stages:
            started_at = time.perf_counter()
            try:
                status = check()
            except SmokeStageError:
                raise
            except Exception as exc:
                raise SmokeStageError(name, type(exc).__name__) from exc
            results.append(
                StageResult(
                    name=name,
                    status=status,
                    duration_ms=round((time.perf_counter() - started_at) * 1000),
                )
            )
        return results

    def _check_admin_ui(self) -> str:
        index = self._get("admin_ui", f"{self._admin_url}/")
        if "Family AI" not in index.text:
            raise SmokeStageError("admin_ui", "expected application marker is missing")
        for asset in ("/admin-assets/admin.css", "/admin-assets/js/app.js"):
            response = self._get("admin_ui", f"{self._admin_url}{asset}")
            if not response.content:
                raise SmokeStageError("admin_ui", f"empty asset: {asset}")
        return "passed"

    def _check_gateway_database(self) -> str:
        response = self._get("gateway_database", f"{self._gateway_url}/v1/agents")
        try:
            agents = response.json()["items"]
        except (KeyError, TypeError, ValueError) as exc:
            raise SmokeStageError("gateway_database", "invalid agent response") from exc
        if not agents:
            raise SmokeStageError("gateway_database", "database returned no active agents")
        return "passed"

    def _check_llm(self) -> str:
        response = self._post(
            "llm",
            f"{self._admin_url}/api/studio/agent-test",
            auth=self._auth,
            json={
                "agent_id": self._settings.default_agent_id,
                "prompt": "Ответь одним коротким словом: готово.",
            },
        )
        try:
            final_response = response.json()["final_response"].strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise SmokeStageError("llm", "invalid studio response") from exc
        if not final_response:
            raise SmokeStageError("llm", "model returned an empty response")
        return "passed"

    def _check_tts(self) -> str:
        response = self._post(
            "tts",
            f"{self._admin_url}/api/studio/speech",
            auth=self._auth,
            json={"text": SMOKE_TEXT, "voice": self._settings.tts_voice},
        )
        content_type = response.headers.get("content-type", "").split(";", maxsplit=1)[0]
        if not content_type.startswith("audio/") or len(response.content) < 128:
            raise SmokeStageError("tts", "synthesis did not return playable audio")
        self._audio = (response.content, content_type)
        return "passed"

    def _check_stt(self) -> str:
        if self._audio is None:
            raise SmokeStageError("stt", "synthetic TTS sample is unavailable")
        content, content_type = self._audio
        extension = "wav" if "wav" in content_type else "mp3"
        response = self._post(
            "stt",
            f"{self._admin_url}/api/studio/transcription",
            auth=self._auth,
            files={"file": (f"smoke.{extension}", content, content_type)},
        )
        try:
            transcript = response.json()["text"].strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise SmokeStageError("stt", "invalid transcription response") from exc
        if not transcript:
            raise SmokeStageError("stt", "speech recognition returned empty text")
        return "passed"

    def _check_vision(self) -> str:
        if self._settings.vision_provider == "disabled":
            return "skipped"
        response = self._post(
            "vision",
            f"{self._admin_url}/api/studio/vision",
            auth=self._auth,
            data={"question": VISION_QUESTION},
            files={"file": ("smoke.png", _solid_png(), "image/png")},
        )
        try:
            description = response.json()["description"].strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise SmokeStageError("vision", "invalid image response") from exc
        if not description:
            raise SmokeStageError("vision", "image understanding returned empty text")
        return "passed"

    def _get(self, stage: str, url: str, **kwargs: object) -> httpx.Response:
        return self._request(stage, "GET", url, **kwargs)

    def _post(self, stage: str, url: str, **kwargs: object) -> httpx.Response:
        return self._request(stage, "POST", url, **kwargs)

    def _request(
        self,
        stage: str,
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        try:
            response = self._client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            raise SmokeStageError(stage, f"HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise SmokeStageError(stage, type(exc).__name__) from exc


def _solid_png(width: int = 32, height: int = 32) -> bytes:
    """Build a tiny deterministic blue PNG without adding an image dependency."""

    signature = b"\x89PNG\r\n\x1a\n"
    raw_rows = b"".join(b"\x00" + bytes((45, 120, 220)) * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        payload = kind + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        signature
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw_rows))
        + chunk(b"IEND", b"")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-url", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-url", default="http://127.0.0.1:8001")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    settings = Settings()
    try:
        with httpx.Client(timeout=args.timeout) as client:
            results = ReleaseSmokeRunner(
                client,
                settings,
                gateway_url=args.gateway_url,
                admin_url=args.admin_url,
            ).run()
    except SmokeStageError as exc:
        print(json.dumps({"status": "failed", "stage": exc.stage, "reason": exc.reason}))
        return 1

    for result in results:
        print(f"[{result.status.upper()}] {result.name} {result.duration_ms}ms")
    print(json.dumps({"status": "passed", "stages": [asdict(item) for item in results]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
