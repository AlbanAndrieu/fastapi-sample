# Homelab security and resilience roadmap

This roadmap turns `/sickz`, `/healthz`, the TrueNAS read-only runtime inventory, and the declared Nabla service topology into actionable security and availability controls.

## P0 — Public exposure policy

- **pfSense administration (`10443/tcp`)**: allow only from trusted LAN/VPN administration paths. A successful probe from FastAPI Cloud or another Internet vantage point is a security failure.
- **TrueNAS HTTPS/API (`7000/tcp`)**: currently an intentional direct publication through pfSense HAProxy. The path is `Internet -> pfSense WAN:7000 -> HAProxy TLS termination -> TrueNAS 172.17.0.24:7000 over TLS`. This path does **not** use Cloudflare Tunnel and must remain narrowly scoped to the dedicated HAProxy listener/rule.
- **TrueNAS SSH (`9922/tcp`) and firewall SSH (`22/tcp`)**: external reachability is always a failure.
- Remove broad WAN pass rules such as an Easy Rule that permits arbitrary inbound TCP. Every public listener must have an explicit port/service policy.
- Keep Cloudflare Tunnel evidence distinct from direct HAProxy/Traefik exposure. `tunnelSecure=true` means a Cloudflare-protected exposure is expected; direct exceptions must remain auditable and visible as security debt.

## P0 — Health endpoint reliability

- `/healthz` must not return an unhandled HTTP 500 because a probe implementation and its orchestration disagree on a function signature.
- Keep an explicit regression test for the `probe_name=` contract used by the health orchestrator.
- Optional/deep dependency failures must be represented as structured probe diagnostics (`reachable`, HTTP status, error kind, latency) rather than uncaught exceptions.
- Production deployment remains gated by the full pytest suite and source-size refactoring thresholds; do not relax the `<400` health/Sickz JavaScript threshold to unblock a deployment.

## P1 — DNS architecture and resolver resilience

Current risk: making clients depend directly on Pi-hole or AdGuard Home running as a TrueNAS App turns a TrueNAS/Docker outage into a LAN-wide DNS outage even when routing and Wi-Fi are healthy.

Evaluate and document a resilient policy with these goals:

1. Keep **pfSense/Unbound** as a stable recursive/caching resolver and policy anchor available independently from TrueNAS Apps.
2. Decide whether **Pi-hole**, **AdGuard Home**, or both provide filtering upstream/downstream of Unbound; avoid ambiguous client-side DNS ordering that lets clients bypass filtering unpredictably.
3. If filtering resolvers remain client-facing, deploy at least two independent instances on different failure domains rather than two containers on the same TrueNAS host.
4. Define DHCP DNS advertisements, local-zone ownership, DNSSEC behavior, conditional forwarding, and failover semantics explicitly.
5. Add probes for resolver availability and policy correctness, not only TCP/UDP port reachability.
6. Test failure scenarios: TrueNAS reboot, Docker stopped, Pi-hole stopped, AdGuard stopped, Unbound restart, WAN loss, and DNSSEC/upstream failure.

Target principle: a TrueNAS Apps outage may reduce filtering/telemetry but must not by itself remove basic LAN Internet name resolution.

## P1 — Runtime/topology reconciliation

- Reconcile TrueNAS `app.query` state with `nabla-compose/catalog/services.json` and `service-topology.json`.
- Highlight required dependency violations separately from a container-level `RUNNING` state. For example, a logical service must not be shown healthy when a required database/cache/object-store dependency is stopped.
- Report unmanaged TrueNAS Apps explicitly; do not guess their dependency order until their Compose metadata is represented in the topology catalog.
- Derive restart waves from **required** topology edges before optional observability/exposure edges.

## P1 — TrueNAS host capacity guardrail

A host with an AMD Ryzen 7 7700 must not proceed with mass application reconciliation when the operating system exposes only CPU 0. Add an operational check comparing expected hardware inventory with host-visible CPU count and Docker `NCPU`; block or warn before app redeploy when the counts are implausibly low.

## P2 — Exposure observability

- Surface the expected/observed state of `10443`, `7000`, `9922`, `4000`, `22`, and other reviewed ports in `/sickz`.
- Include the exposure mechanism (`LAN-only`, `HAProxy direct`, `Cloudflare Tunnel`, `Traefik direct`) in diagnostics rather than inferring it only from the hostname.
- Correlate Cloudflare Tunnel/Access evidence, TrueNAS runtime state, application-level HTTP checks, and pfSense port policy without treating any one signal as authoritative for every service.
