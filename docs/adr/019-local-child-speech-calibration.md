# Local child-speech calibration

## Status

Accepted

## Context

Whisper settings must be selected using real child speech. Synthetic TTS is too
clean to represent Lera's pronunciation, pauses and background noise. Ordinary
voice messages are intentionally not retained, so they cannot silently become
a training or benchmark corpus.

The parent should not need to copy, rename or delete audio files manually.

## Decision

Add an explicit, parent-armed calibration workflow:

- Admin starts one temporary calibration session and shows its progress;
- Android discovers only an explicitly active session;
- the app plays a known phrase, waits for playback to finish and records Lera's
  repetition through the existing `VoiceSession` abstraction;
- Android uploads each recording to Gateway with the opaque session and prompt
  identifiers;
- Gateway forwards audio to the bearer-protected Speech Service without
  persisting it;
- Speech Service stores temporary samples with random identifiers in a
  dedicated runtime directory outside Git;
- after collection, Speech compares `beam_size` 1, 3 and 5 with VAD enabled and
  disabled using the same loaded Whisper model;
- production requests and calibration trials share the serialized inference
  lock, but the benchmark releases it between trials so queued voice requests
  can proceed;
- the result contains only aggregate accuracy, latency and silence-rejection
  metrics;
- all sample audio is deleted after completion, cancellation, failure or the
  configured expiry period.

The calibration set contains prompted speech and silence checks. Expected text
is server-controlled and never derived from an unverified transcription.

## Alternatives

- Benchmark generated TTS: rejected because it substantially overestimates
  child-speech quality.
- Save ordinary conversations automatically: rejected because collection must
  be explicit and purpose-limited.
- Put samples in Git or cloud storage: rejected for privacy.
- Run a second Whisper model process: rejected because the J3710 lacks spare CPU
  and memory.

## Consequences

- The parent only starts the workflow and gives the phone to Lera.
- Calibration temporarily increases Speech Service load and can take tens of
  minutes on the current CPU.
- A service restart can interrupt the benchmark, but persisted session metadata
  allows the parent to cancel or start again.
- Aggregate results remain available after WAV deletion and can guide a
  deliberate configuration change.
