# Synthetic operational verification without child data

## Status

Accepted

## Context

Real child testing is temporarily unavailable, but Speech performance and the
operational alert lifecycle still need repeatable verification. Replaying a child's
recordings, creating synthetic conversations, filling a production disk or forcing
service failures would create unnecessary privacy and availability risks.

## Decision

Add two separate verification mechanisms:

1. A bounded CLI voice benchmark calls only the protected stateless Admin studio.
   It runs fixed synthetic TTS-to-STT phrases and a fixed LLM probe at concurrency
   1, 2 and 4 while reading existing local metrics. Reports contain aggregates and
   synthetic phrase identifiers, never payloads.
2. A protected Admin self-test evaluates alert transitions against controlled
   snapshots in a disposable in-memory SQLite database. It cannot write to the
   production alert table or manipulate real metrics.

The CLI compares message counts before and after a run to enforce the stateless
contract. Heavy benchmark execution is deliberately not exposed as an Admin button:
it is an explicit operator command and must not occupy a web worker accidentally.

## Alternatives

- Reusing child recordings was rejected because it is unnecessary and would expand
  retention and access to personal data.
- Running benchmark turns through the public conversation API was rejected because
  it would create history, media and misleading learning context.
- Triggering production alerts by filling disk or stopping services was rejected as
  disproportionate for lifecycle validation.
- A general-purpose load-test dependency was rejected; bounded concurrency and
  percentile calculation are small enough to implement with the standard library
  and the existing HTTP client.

## Consequences

Voice regressions and queue saturation can be measured before a child test device is
available, and alert behavior can be checked safely from Admin. Synthetic TTS-to-STT
does not model a six-year-old child's pronunciation, microphone, room acoustics or
Android playback latency, so it complements but never completes the real-use
stabilization stage.
