# Project infrastructure monitoring with node exporter

## Status

Accepted

## Context

The protected parent Admin UI needs operational visibility into the project
servers: `family-ai-gateway`, `family-ai-db`, and the local voice workload on
`family-ai-speech`. The required snapshot includes uptime, CPU, memory, root
filesystem usage and PostgreSQL health. Proxmox hosts, Ceph and unrelated
cluster workloads are outside the product boundary.

The deployment is small enough that a separate time-series database would add
more operational cost than value. Reading Linux pseudo-files over SSH would
also couple the application to privileged credentials and unstable command
output.

## Decision

Install the standard Prometheus node exporter on every project server. The
Admin backend fetches only private `/metrics` endpoints and converts selected
samples into a stable protected REST response at `GET /api/infrastructure`.
The Speech exporter and its Admin API card are delivered with the local STT/TTS
service. The protected dashboard therefore covers all three project servers.

The database state is collected separately through the existing SQLAlchemy
connection. It includes query latency, PostgreSQL uptime and version, database
size, and connection utilization. Raw exporter payloads, database errors and
credentials are never sent to the browser.

Exporter URLs and timeouts remain environment configuration. Exporter ports on
the database and Speech servers are restricted to the Gateway address. Short
chart history exists only in the browser session and is not persisted.

## Alternatives

- Prometheus and Grafana: rejected for the first release because this small
  deployment does not justify another persistent monitoring service.
- Proxmox API: rejected because physical nodes, Ceph and unrelated guests are
  explicitly outside the Family AI product boundary.
- Custom SSH or `/proc` agent: rejected to avoid privileged credentials and a
  bespoke monitoring protocol.

## Consequences

Positive consequences:

- standard low-overhead host metrics with no custom agent code;
- no SSH keys or privileged host access inside the application;
- stable and testable Admin API independent of the browser;
- Prometheus can be introduced later without replacing node exporter.

Negative consequences:

- one lightweight exporter service must be maintained on every project server;
- current charts are session-local and disappear after a page reload;
- exporter network access must be restricted separately from Admin auth.
