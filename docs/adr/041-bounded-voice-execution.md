# Bounded voice execution

## Status

Accepted

## Context

The Stage 19 production benchmark on the J3710 Speech host completed all turns,
but total p95 increased from 14.5 seconds with one client to 25.0 seconds with
two and 49.0 seconds with four. At four clients the Speech queue reached three
and CPU p95 reached 94.4%. Unbounded retries or abandoned mobile streams can
therefore make every child wait longer without increasing useful throughput.

The limit must cover voice, multimodal voice and replay synthesis uniformly.
It must not be embedded in an STT or TTS adapter because those providers are
replaceable.

## Decision

- AI Gateway owns a process-local admission controller at its HTTP boundary.
- At most two complete voice turns are admitted by default. This permits one
  active Speech inference and one waiting turn observed in the Stage 19 safe
  range. A third turn receives HTTP 429 before provider work starts.
- One random `X-Request-ID` can be admitted only once while active and for five
  minutes after completion. A duplicate receives HTTP 409.
- The admission lease covers upload validation, STT, LLM, TTS and the complete
  streaming response. Closing a stream releases it in a `finally` block.
- Provider-neutral stage budgets default to 35 seconds for STT, 20 seconds for
  LLM and 30 seconds for TTS. Exceeding one produces HTTP 504 or a child-safe
  streaming error.
- Capacity and budgets are validated settings managed through the existing
  Admin preview, revision, restart and rollback lifecycle.
- Observability stores counters and request stages only. It never records
  audio, images, transcripts or generated answers.

## Alternatives

- An unbounded Gateway queue: rejected because it converts overload into long,
  invisible waits and retains request bodies longer.
- A queue inside Speech Service only: rejected because LLM, replay TTS and
  multimodal work would bypass a shared policy.
- Redis-backed distributed admission: deferred because production has one
  Gateway process and another stateful dependency is not justified.
- Four concurrent turns: rejected by the measured 49-second p95 and queue depth
  of three on the current host.
- One concurrent turn: rejected because the measured two-client mode remained
  successful and a short bounded wait is preferable to rejecting normal overlap.

## Consequences

- Overload is rejected quickly and explained safely in Android.
- Duplicate taps do not repeat STT, LLM or TTS work.
- Leaving the voice screen frees capacity when the stream is cancelled.
- A Gateway restart clears active and recent request IDs. This is acceptable:
  request IDs are transport idempotency guards, not durable business records.
- Multiple Gateway workers would each enforce their own capacity. A future
  scale-out deployment must move admission behind a shared implementation
  without changing the router-facing interface.
