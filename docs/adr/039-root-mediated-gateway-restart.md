# Root-mediated Gateway restart request

## Status

Accepted

## Context

Admin applies a validated Gateway configuration atomically and must restart
the fixed `family-ai-gateway.service` before it can verify readiness. Admin runs
as `familyai-deploy` with `NoNewPrivileges=true`; allowing that web process to
invoke `sudo` would either fail or weaken the service sandbox.

## Decision

Admin writes a random 128-bit nonce to
`/var/lib/family-ai-config/gateway/restart.request` using an atomic rename. A
root-owned `family-ai-gateway-admin.path` activates a oneshot service. Its fixed
helper validates the nonce, restarts only `family-ai-gateway.service`, and
writes the same nonce to `restart.ack` after systemd reports success.

Admin accepts the restart only after reading its own nonce from the
acknowledgement, checking that the fixed unit is active, and receiving HTTP 200
from the loopback `/healthz` endpoint. The browser cannot supply a command,
unit name, path, or nonce. Requests and acknowledgements remain in the closed
runtime directory and contain no secret configuration values.

The release installer owns the helper and both units. It removes the obsolete
`family-ai-admin` sudoers file. The separate release controller retains its
narrow operator sudoers contract; that contract is not reachable by Admin
because `NoNewPrivileges=true` remains enabled.

## Alternatives

- Disable `NoNewPrivileges` and call `sudo`: rejected because the web process
  would regain a privilege-escalation path.
- Expose a privileged HTTP or D-Bus service: rejected as unnecessary surface
  area for one fixed local action.
- Restart manually over SSH: safe, but it would make atomic apply and automatic
  rollback impossible from Admin.

## Consequences

Gateway restart remains automatic without granting elevated execution to the
web process. The helper is intentionally limited to one service and its path
unit must be installed on every Gateway host. A restart request can time out;
the configuration lifecycle then restores the previous environment and issues
a separate compensating restart request.
