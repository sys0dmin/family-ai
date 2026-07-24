# Formal Safety Policy Engine

## Status

Accepted

## Context

The Gateway already checked child input and model output, but decisions were
spread across helper methods and several capabilities. Rule names were not one
stable contract, tool and permission checks were implicit, and the parent could
not see which protections were active without reading source code.

The platform needs explainable child-safety decisions without sending another
request to an LLM, storing child text in metrics, or allowing an Admin mistake
to disable mandatory protection.

## Decision

Introduce a deterministic `SafetyPolicyEngine` owned by the AI Gateway.
Every evaluation returns a `PolicyOutcome` with one of three actions:
`ALLOW`, `TRANSFORM`, or `BLOCK`. Every decision contains a stable rule ID,
phase, category and non-sensitive reason.

Policies have four explicit phases:

- input before any provider call;
- output before content is returned to the child;
- tool before a capability adapter is used;
- permission before agent-scoped exceptional guidance is allowed.

Mandatory descriptors are held in one catalog. Agent tools and permissions
remain versioned configuration, but they cannot invent or disable policy rules.
The existing `SafetyService` stays as a compatibility facade while callers move
to the formal outcome contract.

Gateway stores only in-memory counters keyed by rule ID. It exposes catalog and
counters through a loopback-only internal endpoint. The protected Admin service
adapts that endpoint and provides:

- a read-only rule catalog with aggregate counts;
- a versioned deterministic scenario matrix;
- reset of aggregate counters;
- navigation to agent tool and permission configuration.

Mandatory rules cannot be disabled or edited in Admin. Prompt safety remains a
defence-in-depth layer, not the source of enforceable business rules.

## Alternatives

- Keep regex checks in unrelated services: rejected because decisions remain
  inconsistent and cannot be inspected as one policy.
- Use a second LLM as safety judge: rejected because results are probabilistic,
  slower, provider-dependent and may disclose child content externally.
- Store every decision with message text in PostgreSQL: rejected because the
  operational goal only needs aggregate evidence and should minimize retained
  child data.
- Allow policy toggles in Admin: rejected because a UI error must not disable a
  mandatory child-safety guarantee.
- Add a separate policy service now: rejected because current load and rule
  complexity do not justify another deployable component.

## Consequences

- Safety decisions are explainable and independently testable.
- Benign educational mentions are not blocked only because of a single word.
- Metrics are process-local and reset when Gateway restarts or an Admin
  explicitly clears them; this is intentional for the current home deployment.
- Adding a rule requires a catalog entry, deterministic implementation and
  scenario coverage.
- A future external policy service can adopt the same outcome contract without
  changing conversation or capability APIs.
