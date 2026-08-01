# Refresh-safe admin browser session

## Status

Accepted

## Context

The Admin UI previously kept its HTTP Basic authorization value only in a
JavaScript variable. Refreshing the page erased that value and returned the
parent to the login form. Persisting reusable Basic credentials in browser
storage would expose the password to JavaScript.

## Decision

After a successful Basic-authenticated login, Admin issues a signed,
time-limited, same-origin HttpOnly cookie. Protected endpoints accept either
valid Basic credentials or that cookie. The token contains only its issue time
and an HMAC signature derived from the current admin username and password.

Unauthorized API responses deliberately omit `WWW-Authenticate: Basic`.
The Basic value is sent only by the page login form for the session exchange;
the browser must not replace that form with its native authentication dialog.

The cookie uses `SameSite=Strict`, is unavailable to JavaScript and expires
after the configurable `FAMILY_AI_ADMIN_SESSION_TTL_HOURS` period. HTTPS
requests additionally receive the `Secure` attribute. Explicit logout removes
the cookie. Changing the admin password invalidates every previously signed
session automatically.

## Alternatives

- Store the Basic header in `localStorage` or `sessionStorage`: rejected
  because JavaScript-readable storage would contain reusable credentials.
- Ask the browser to manage native Basic authentication: rejected because the
  custom login experience and explicit logout would become inconsistent.
- Store sessions in PostgreSQL or Redis: rejected because a single-parent home
  admin panel does not need persistent server-side session infrastructure.

## Consequences

- Refreshing the Admin UI no longer requires another login.
- The password is not stored in browser-accessible storage.
- Sessions reset after their lifetime, logout or password change.
- Plain HTTP on the trusted home network cannot use a `Secure` cookie; HTTPS
  remains preferable if the Admin UI is ever exposed beyond that network.
