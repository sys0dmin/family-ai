"""Narrow operational controls exposed to the protected admin panel."""

import logging
import subprocess
import time
from dataclasses import dataclass
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
    """Restart only the known Gateway unit without invoking a shell."""

    service_name = "family-ai-gateway.service"
    restart_command = (
        "/usr/bin/sudo",
        "-n",
        "/usr/bin/systemctl",
        "restart",
        service_name,
    )
    status_command = (
        "/usr/bin/systemctl",
        "is-active",
        "--quiet",
        service_name,
    )
    health_url = "http://127.0.0.1:8000/healthz"

    def restart_gateway(self) -> GatewayRestartResult:
        try:
            restart = subprocess.run(
                self.restart_command,
                check=False,
                capture_output=True,
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.exception("gateway_restart_command_failed")
            raise GatewayRestartError("Gateway restart command failed") from exc
        if restart.returncode != 0:
            logger.error(
                "gateway_restart_rejected",
                extra={"returncode": restart.returncode},
            )
            raise GatewayRestartError("Gateway restart was rejected")

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
