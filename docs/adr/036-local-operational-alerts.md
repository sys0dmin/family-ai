# Local privacy-safe operational alerts

## Status

Accepted

## Context

Admin UI already collects node, PostgreSQL and voice-pipeline metrics, but a parent
must interpret every number manually. Family AI needs early warnings and a small
technical history without expanding monitoring to the Proxmox cluster or exporting
child data.

## Decision

Add an operational alert evaluator to Admin. A protected aggregate scan endpoint
collects each existing source once, evaluates configurable allowlisted thresholds,
and stores alert episodes in PostgreSQL. An episode remains visible after
acknowledgement and is resolved only when the signal recovers. Resolved episodes are
retained for a configurable 30-day window.

The persisted model accepts only technical scope, metric, severity, generated
description, numeric value and timestamps. It has no conversation, message, media or
turn foreign keys. The Admin infrastructure tab performs the scan every 15 seconds
while open.

## Alternatives

- Prometheus and Alertmanager were rejected because the requested scope is the three
  Family AI services, not the home cluster, and another stack is unnecessary here.
- Browser-only warnings were rejected because acknowledgement and recovery history
  would disappear on refresh.
- Reusing conversation history was rejected because operational events must not be
  coupled to child data retention or provider behavior.
- A permanent background scheduler was deferred because it introduces another
  runtime responsibility. This iteration is explicitly scan-on-open.

## Consequences

The parent gets actionable local warnings, acknowledgement and recovery history
without external data flow. Threshold changes require environment configuration and
an Admin restart. Warnings are not evaluated while the Admin infrastructure screen
is closed; continuous alerting can later call the same evaluator from a replaceable
local scheduler without changing its persistence model or UI contract.
