# Runtime release passport

## Status

Accepted

## Context

The deployment controller installs immutable Git releases, but Admin currently
shows only host and provider health. A healthy process may still run an
unexpected release, an old database revision or configuration loaded before a
restart. The Android APK also has reproducible build metadata, but the server
cannot observe which build is actually making requests.

Version diagnostics must not require Git repositories on production hosts,
expose configuration values, identify a device, or add a remote monitoring
dependency.

## Decision

- Each service reads the immutable `release.json` bundled by the release
  builder and compares its commit with the controller-owned
  `/srv/family-ai/<component>/deployed-version` marker.
- Gateway exposes its identity only through a loopback endpoint. Speech adds
  identity to its existing authenticated runtime metrics contract.
- Runtime identity contains component, application version, actual and expected
  commit, match state and process uptime.
- Gateway computes a SHA-256 fingerprint from canonical non-secret effective
  settings. Secret values and the database URL are excluded before hashing.
- Admin compares the Gateway fingerprint with its own effective configuration,
  reads the current Alembic revision from PostgreSQL and the code head from the
  active release, then exposes one authenticated release-passport API.
- Release Android builds receive version and source commit through compile-time
  Dart definitions. Requests carry only those two build-wide values. Gateway
  retains the last observed build in process memory without a device ID, user
  ID, conversation ID or durable database record.
- Admin displays `aligned`, `drift` and `unavailable` explicitly. Missing
  telemetry is not presented as a match.

## Alternatives

- Read Git metadata in production: rejected because release archives do not and
  should not contain `.git`.
- Derive the commit only from the `current` symlink: rejected because it cannot
  detect divergence from the deployment controller marker.
- Store every Android device and version in PostgreSQL: rejected because the
  project needs a release observation, not child or device tracking.
- Hash the complete environment including secrets: rejected because even a hash
  should not become an oracle for low-entropy credentials.
- Query GitHub or another external release service: rejected because the home
  deployment must remain independently operable.

## Consequences

- Admin can distinguish healthy-but-wrong code from an unavailable component.
- Configuration drift is visible without revealing any configuration value.
- The observed Android build disappears after a Gateway restart until an app
  sends another request; the UI labels this state as unavailable.
- A release manifest or deployed-version marker missing in development produces
  an explicit unavailable identity rather than a fabricated commit.
- The contracts remain replaceable: another deployment system can provide the
  same actual/expected identity without changing Admin UI.
