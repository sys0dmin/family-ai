# Modular clients and build-time drift guards

## Status

Accepted

## Context

Admin UI, child web UI and Android evolved quickly and accumulated large
composition files. Character artwork also has to exist in both Gateway and APK
archives, which created two editable copies. These issues did not break the
runtime, but made unrelated changes risky and allowed silent release drift.

## Decision

- Python and JavaScript entrypoints are composition roots; feature routers and
  screens own their endpoints, state and rendering.
- Flutter keeps its existing public classes while transport helpers, screen
  widgets and voice-turn execution live in separate library parts.
- `gateway/static/assets/characters` is the canonical artwork source.
  `mobile/assets/characters` is a release mirror verified by SHA-256 and updated
  only by `scripts/assets/sync_character_assets.py --write`.
- The local release gate audits both exact uv lock graphs. The PyTorch CPU local
  version is normalized only for advisory lookup; the installed lock is never
  rewritten.
- A dedicated migration harness creates and destroys a uniquely named
  PostgreSQL database. It refuses an admin URL targeting the application DB.

## Alternatives

- Keep large files and rely on reviews. Rejected because regressions already
  crossed feature boundaries.
- Load mobile artwork over HTTP. Rejected because the child interface must work
  predictably on the home network and the APK needs local assets.
- Add a shared frontend build tool. Rejected because it adds Node.js and a new
  supply chain without product value.
- Test migrations against production. Rejected because schema verification must
  be disposable and isolated.

## Consequences

Feature changes have smaller review surfaces and existing runtime contracts stay
unchanged. Release archives still contain duplicate artwork by design, but drift
now fails before release. Dependency auditing needs advisory-network access.
The real migration stage needs a PostgreSQL role allowed to create temporary
databases; it never uses or drops the Family AI application database.
