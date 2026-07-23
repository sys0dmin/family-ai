# Local CPU speech service

## Status

Accepted

## Context

The voice-first child interface depends on cloud STT and TTS quotas. A TTS
quota exhaustion currently makes the complete voice turn fail even when speech
recognition and the language model succeed. The home Proxmox cluster has a
dedicated `family-ai-speech` LXC with four Intel J3710 CPU cores, 6 GB RAM and
no GPU or AVX2 support.

Benchmarks on the production LXC used the same 4.1-second Russian phrase:

- `faster-whisper small` INT8: 33.8 seconds;
- `faster-whisper base` INT8: 9.9 seconds;
- `faster-whisper tiny` INT8: 4.5 seconds;
- `whisper.cpp base-q5_1`: 29.4 seconds;
- `whisper.cpp small-q5_1`: exceeded 120 seconds;
- Silero `v5_2_ru`: 1.7 seconds after warm-up.

`small` and `medium` do not meet interactive latency requirements on this CPU.
`tiny` is faster but presents a higher accuracy risk for a young child's
natural speech.

## Decision

Run an independent FastAPI Speech Service on `family-ai-speech`. It exposes the
OpenAI-compatible endpoints `/v1/audio/transcriptions` and `/v1/audio/speech`
so the Gateway keeps using its existing provider adapter.

Use persistent CPU models:

- `faster-whisper base` with INT8, four threads, beam size 1 and VAD for STT;
- Silero `v5_2_ru` at 48 kHz for Russian TTS.

Serialize STT and TTS inference to prevent CPU oversubscription. Keep model
loading and provider-specific voice aliases inside the Speech Service. Protect
audio endpoints with a dedicated bearer token and restrict port `8010` to the
Gateway address at the network layer. Do not store source audio or synthesized
responses in the Speech Service.

The cloud speech provider remains a manual configuration fallback. Automatic
fallback is deferred because silently sending child audio outside the home
network would make privacy behavior less predictable.

## Alternatives

- `faster-whisper small` or `medium`: rejected because measured latency is
  already excessive for `small`; `medium` is larger and slower.
- `faster-whisper tiny`: retained as an operational tuning option, but not the
  default because child-speech accuracy matters more than five seconds saved.
- `whisper.cpp`: rejected on this CPU after direct production benchmarking.
- Piper TTS: retained as a future lightweight fallback, but Silero produced a
  more suitable Russian voice within the available latency budget.
- XTTS v2: rejected because CPU and memory cost are disproportionate for the
  J3710 cluster.
- Embed models in the Gateway: rejected to keep model dependencies, resource
  limits and deployment lifecycle isolated.

## Consequences

Positive consequences:

- voice recognition and synthesis work without cloud quotas;
- child audio stays in the home network;
- Gateway integration is configuration-only;
- STT and TTS engines can be replaced without changing clients or conversation
  business logic.

Negative consequences:

- local STT adds roughly ten seconds for a short phrase on current hardware;
- the service adds model, Python and systemd maintenance;
- only one inference request can run at a time;
- switching back to cloud speech is currently an explicit admin operation.
