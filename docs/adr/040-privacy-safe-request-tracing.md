# Privacy-safe request tracing

## Status

Accepted

## Context

Voice metrics show aggregate STT, Vision, LLM and TTS latency, but cannot join
the stages of one failed Android turn. Gateway and Admin run as separate
processes, so an in-memory registry would make diagnostics invisible to Admin.
Using conversation history would mix operational data with child content and
would make a support bundle unsafe to share.

## Decision

- Android assigns a random UUID v4 to each turn in `X-Request-ID`; Gateway
  validates it or creates one for backward-compatible clients.
- Provider request DTOs carry the UUID through the existing LLM, STT, TTS and
  Vision abstractions. Provider-specific code only maps it to a transport
  header.
- Gateway records an allow-list of technical events: mode, stage, status,
  timestamps, duration, error code and service. Content and domain identifiers
  are not accepted by the repository API.
- A bounded host-local SQLite repository is shared by Gateway and Admin. It
  keeps at most 200 traces for 24 hours under
  `/var/lib/family-ai-diagnostics`.
- Admin exposes authenticated failed-turn timelines and a redacted JSON bundle
  with explicit privacy metadata and `no-store` caching.
- The repository remains behind `RequestTraceRegistry`, so a future telemetry
  backend can replace SQLite without changing routers or providers.

## Alternatives

- In-process memory: rejected because Gateway and Admin cannot share it.
- PostgreSQL tables: rejected because short-lived operational diagnostics do
  not belong to child history or configuration and would require a migration.
- OpenTelemetry collector and a separate observability stack: deferred as too
  heavy for the current three-node home deployment.
- Plain JSONL: rejected because concurrent process writes, pruning and complete
  bundle reads would require a custom locking and compaction protocol.

## Consequences

- A parent can locate the failed stage without reading messages or media.
- Diagnostics survive process restarts for up to 24 hours but are not a backup.
- Both services need write access to one protected runtime directory.
- SQLite adds no third-party dependency, but its file and WAL are mutable host
  state and must remain outside release archives and Git.
- External providers may log the random request header according to their own
  policy; it contains no Family AI user, conversation or message identifier.
