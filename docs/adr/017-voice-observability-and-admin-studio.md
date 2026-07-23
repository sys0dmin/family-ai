# Voice pipeline observability and protected test studio

## Status

Accepted

## Context

The production voice turn crosses Android recording, local STT, the external
language model and local TTS. Host CPU metrics show that `family-ai-speech` is
busy, but they do not explain which stage the child is waiting for, whether a
request is queued, how long the recording was, or why recognition failed.

The parent also needs to validate an agent prompt, the deterministic safety
result and a configured voice without adding synthetic messages to the child's
retained conversation history.

Audio and message content must not be added to operational telemetry.

## Decision

Add application-level observability without introducing a time-series database:

- Gateway keeps a bounded in-memory window of anonymized voice-turn samples;
- each sample contains recording, STT, LLM, TTS and total duration, status,
  confidence and an optional error stage;
- Gateway exposes only the aggregate snapshot and recent numeric samples on a
  loopback-only internal endpoint;
- Speech Service exposes a bearer-protected runtime snapshot with queue depth,
  active inference stage, calls, failures, queue wait and processing duration;
- Admin fetches both internal snapshots server-side and presents one protected
  voice operations view;
- metrics reset on service restart and never contain transcript, response text,
  conversation id, child profile id or audio.

Use OpenAI-compatible `verbose_json` transcription responses. The local Speech
Service reports standard segment timestamps, log probability and no-speech
probability. Gateway derives decoded recording duration, post-VAD speech
duration and a diagnostic confidence estimate from that provider-neutral
response.

Add configurable Russian initial-prompt vocabulary and conservative silence
rejection to the local STT adapter. Confidence remains diagnostic and uses a
low configurable threshold because Whisper probabilities are not calibrated
for a six-year-old child's speech.

Add a protected Admin test studio:

- it loads the selected published agent and global safety baseline;
- it performs a stateless LLM turn without creating a conversation or message;
- it returns raw model text, final text, safety decision and stable rule id;
- a separate endpoint synthesizes a short preview with the selected voice;
- neither operation stores test text or generated audio.

Android sends its measured recording duration as an optional multipart field.
Older clients remain compatible, and decoded STT duration is used when the
client value is absent.

## Alternatives

- Persist every voice span in PostgreSQL: rejected because current operational
  diagnostics do not need long retention and should not grow the product data
  model.
- Add Prometheus and Grafana: deferred until bounded runtime metrics are
  insufficient for the three-server home deployment.
- Log transcript and raw model response for debugging: rejected for child
  privacy.
- Use a second LLM call to classify every safety response: rejected because it
  adds latency, cost and another failure mode. Deterministic rules remain the
  enforcement boundary.
- Store Studio tests as normal conversations: rejected because parent
  diagnostics must not pollute Lera's history or analytics.

## Consequences

Positive consequences:

- the parent can distinguish recording, STT, LLM, TTS and queue delays;
- STT tuning can be based on measured production behavior;
- silence and low-confidence recognition are visible without retaining audio;
- agent and voice changes can be tested before use by the child;
- no new persistent infrastructure is required.

Negative consequences:

- operational history resets when Gateway or Speech Service restarts;
- confidence is a diagnostic estimate rather than a calibrated probability;
- Admin depends on two private runtime endpoints;
- the protected Studio can consume real provider quota and CPU.
