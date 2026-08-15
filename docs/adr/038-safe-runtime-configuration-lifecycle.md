# Safe runtime configuration lifecycle

## Status

Accepted

## Context

The protected Admin UI can edit Gateway provider, speech, Vision, music and
retention settings in `/etc/family-ai/gateway.env`. The previous implementation
rewrote that file in place, did not keep a recoverable revision and required a
separate manual Gateway restart. A syntactically valid but unusable provider URL
or model could therefore leave the child-facing service unavailable until an
operator repaired the file manually.

The environment file also contains unrelated and more sensitive operational
settings: the database URL, Admin credentials and monitoring endpoints. A
configuration rollback must never replace those values as a side effect.

## Decision

Gateway Admin owns a small file-backed configuration lifecycle for the exact
allow-list of fields already editable on the Settings screen.

- A preview validates the candidate with the normal `Settings` model and returns
  only a redacted diff.
- Apply writes the complete environment file through a `0600` temporary file and
  an atomic replace.
- The Gateway service is restarted and its loopback `/healthz` endpoint must
  become ready before the revision is accepted.
- If restart or readiness fails, the previous managed values are restored,
  Gateway is restarted again and the failed attempt is recorded as rolled back.
- Successful managed values are stored under
  `/var/lib/family-ai-config/gateway` as bounded local snapshots with mode `0600`.
- Metadata contains no secret values. Provider credentials are represented only
  as `configured` or `not configured`.
- Rollback restores only the managed allow-list. Database, Admin authentication,
  monitoring and deployment variables remain untouched.

Speech keeps ownership of its own runtime file and control API. Gateway does not
mount or edit Speech storage. Its adapter performs a compensating apply of the
previous validated beam/VAD values if restart verification fails.

## Alternatives

- Store revisions in PostgreSQL: rejected because recoverable provider secrets
  would expand database sensitivity and couple host bootstrapping to the DB.
- Snapshot the whole Gateway environment: rejected because rollback could
  unexpectedly change database or Admin credentials.
- Add Vault, Consul or another configuration service: rejected as excessive for
  the three-host home deployment.
- Keep manual `.env` repair as the rollback path: rejected because the Admin UI
  already acts as the operational control plane.

## Consequences

- A bad Admin change is bounded by an automatic health check and rollback.
- Revisions survive application releases but remain local to the Gateway host.
- Disaster recovery still relies on the existing DR kit for the current effective
  environment; revision history is operational convenience, not a backup.
- Provider secrets exist in protected host-local revision files, so directory
  ownership and `0600` permissions are part of the deployment contract.
- Provider correctness beyond process readiness is still checked by Test Studio
  and the release smoke-test; apply does not make paid LLM/TTS/STT calls.
