# Admin-managed Speech runtime

## Status

Accepted

## Context

The parent needs to change the local Whisper `beam_size`, VAD and bounded
decode limit from
the protected Admin UI. The Speech Service runs on another LXC container, so
the Gateway cannot use its local `systemctl` control. Giving the application a
general SSH key or unrestricted remote sudo would violate least privilege and
tightly couple Admin to the current host layout.

The settings must survive a service restart, and Admin must show the values
actually loaded by the new Speech process rather than only reporting that a
file was written.

## Decision

Add a bearer-protected internal Speech runtime-settings API that:

- exposes only the active `stt_beam_size`, `stt_vad_filter` and
  `stt_max_new_tokens`;
- validates beam size as an integer from 1 through 10;
- validates the token limit from 32 through the Whisper context limit of 448;
- atomically writes only these three variables to
  `/var/lib/family-ai-speech/runtime.env`;
- creates one fixed restart-request file in the same private runtime directory.

A systemd drop-in loads the optional runtime env after the main protected env.
A root-owned `.path` unit watches only that request file. Its fixed oneshot unit
removes the request and schedules a restart of only `family-ai-speech.service`
after the HTTP response can leave the old process. The Speech process retains
`NoNewPrivileges=true` and receives no sudo permission.

Gateway uses a server-side adapter for this private API. After applying a
change, it polls until a newly started Speech process reports the requested
values. The browser never receives the Speech bearer token or direct access to
the Speech host.

## Alternatives

- SSH from Gateway to Speech: rejected because it adds remote credentials and
  host-specific command execution to application code.
- Sudo from the Speech process: rejected because `NoNewPrivileges=true` must
  remain enabled and least privilege does not require sudo for a file trigger.
- Change settings only in memory: rejected because values would disappear on
  restart and would not test the real startup configuration.
- Edit `/etc/family-ai/speech.env` directly from Speech: rejected because that
  file contains unrelated secrets and remains root-owned.
- Avoid restart by mutating the loaded backend: rejected because the active
  configuration would diverge from the persistent startup configuration.

## Consequences

- Beam, VAD and the decode limit can be changed and verified from Admin with
  one action.
- Deployment must install one path unit, one fixed oneshot unit and one systemd
  drop-in.
- A failed restart leaves the previous process available until systemd acts;
  Admin reports failure if the requested values do not appear before timeout.
- No API can change models, secrets, paths or arbitrary environment variables.
