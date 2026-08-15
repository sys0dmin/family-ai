"""Narrow operational controls exposed to the protected admin panel."""

import logging
import secrets
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class GatewayRestartError(RuntimeError):
    """Raised when the configured Gateway service could not be restarted."""


@dataclass(frozen=True)
class GatewayRestartResult:
    service: str
    active: bool


class GatewaySystemService:
    """Request a fixed root-mediated Gateway restart and verify its acknowledgement."""

    service_name = "family-ai-gateway.service"
    status_command = (
        "/usr/bin/systemctl",
        "is-active",
        "--quiet",
        service_name,
    )
    health_url = "http://127.0.0.1:8000/healthz"
    default_request_path = Path(
        "/var/lib/family-ai-config/gateway/restart.request"
    )
    default_ack_path = Path("/var/lib/family-ai-config/gateway/restart.ack")

    def __init__(
        self,
        *,
        request_path: Path | None = None,
        ack_path: Path | None = None,
    ) -> None:
        self._request_path = request_path or self.default_request_path
        self._ack_path = ack_path or self.default_ack_path

    def restart_gateway(self) -> GatewayRestartResult:
        nonce = secrets.token_hex(16)
        try:
            self._write_restart_request(nonce)
            self._wait_for_ack(nonce, timeout_seconds=20.0)
        except OSError as exc:
            logger.exception("gateway_restart_request_failed")
            raise GatewayRestartError("Gateway restart could not be requested") from exc

        try:
            active = (
                subprocess.run(
                    self.status_command,
                    check=False,
                    capture_output=True,
                    timeout=5,
                ).returncode
                == 0
            )
        except (OSError, subprocess.TimeoutExpired):
            active = False
        return GatewayRestartResult(
            service=self.service_name,
            active=active,
        )

    def _write_restart_request(self, nonce: str) -> None:
        self._request_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._request_path.with_suffix(".tmp")
        try:
            temporary.write_text(f"{nonce}\n", encoding="ascii")
            temporary.chmod(0o600)
            temporary.replace(self._request_path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _wait_for_ack(self, nonce: str, *, timeout_seconds: float) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                if self._ack_path.read_text(encoding="ascii").strip() == nonce:
                    return
            except FileNotFoundError:
                pass
            time.sleep(0.2)
        raise GatewayRestartError("Gateway restart acknowledgement timed out")

    def restart_gateway_verified(
        self,
        *,
        timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 0.5,
    ) -> GatewayRestartResult:
        """Restart the fixed unit and wait for the child-facing readiness endpoint."""

        result = self.restart_gateway()
        if not result.active:
            raise GatewayRestartError("Gateway service did not become active")

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                request = Request(self.health_url, headers={"Accept": "application/json"})
                with urlopen(request, timeout=2) as response:  # noqa: S310
                    if response.status == 200:
                        return result
            except (OSError, URLError, TimeoutError):
                pass
            time.sleep(poll_interval_seconds)
        raise GatewayRestartError("Gateway readiness check timed out")
