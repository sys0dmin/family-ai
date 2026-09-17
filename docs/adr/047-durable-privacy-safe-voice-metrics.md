# Durable privacy-safe voice metrics

## Status

Accepted

## Context

The first voice observability implementation kept a bounded Gateway window in
process memory. It was useful for a live incident, but reset on deployment or
restart and did not include one-shot replay of an existing answer. After real
child usage, the parent needs to compare STT, LLM and TTS wait time across
days without retaining a child's speech, transcript, images or identifiers.

## Decision

Store one PostgreSQL row per UTC calendar day and voice operation mode in
`voice_daily_metrics`. Each row contains only counters and sums of stage
durations: recording, STT, Vision, LLM, TTS, first ready audio, first client
playback and total duration. The Admin UI calculates averages from these sums.

Both full voice turns and answer replay record an anonymized completed sample.
The in-memory window remains for current diagnostics and recent error stages;
the table is an independent historical aggregate. The archive is best-effort:
a database issue must never make a child-facing request fail.

Rows are retained for `FAMILY_AI_VOICE_METRICS_RETENTION_DAYS` (30 by default).
No per-turn row, request ID, conversation ID, device ID, transcript, audio,
image, model response or raw confidence value is persisted.

## Alternatives

- Persist every request span: rejected because it creates unnecessary child
  metadata and a more complex retention burden.
- Prometheus/Grafana: deferred; daily PostgreSQL aggregates fit the current
  three-container home deployment.
- Keep runtime-only metrics: rejected because restarts hide the trend needed
  for tuning STT and diagnosing perceived voice latency.

## Consequences

The parent can inspect a 30-day, restart-resistant trend in Admin. Historical
data starts at deployment; old raw turns cannot and should not be backfilled.
The view is intended for operational diagnosis, not individual-child tracking.
