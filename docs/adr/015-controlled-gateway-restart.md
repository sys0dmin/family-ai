# Controlled Gateway restart from Admin

## Status

Superseded by [ADR 039](039-root-mediated-gateway-restart.md)

## Context

Admin needs a narrow way to restart the child-facing Gateway after an
operational configuration change. The original implementation invoked one
fixed `sudo systemctl restart family-ai-gateway.service` command.

## Decision

The original decision allowed only that exact command through a dedicated
sudoers rule. It did not accept a service name or command from the browser.

## Consequences

The contract was narrow, but incompatible with the Admin unit's required
`NoNewPrivileges=true` hardening. ADR 039 replaces it with a root-owned systemd
path unit and removes the web process from the privilege-escalation path.
