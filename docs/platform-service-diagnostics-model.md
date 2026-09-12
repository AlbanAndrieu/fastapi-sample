# Platform service diagnostics model

This document defines how `/api` presents Cloudflare, pfSense, DNS and TrueNAS evidence. The goal is to keep operational status, architecture/path context and security telemetry separate so that an unavailable observer cannot accidentally become a false service outage.

## UI ownership

### Service Cards are canonical

A service Card on the health board is the canonical operational representation of that service/provider. Its **Service diagnostics** drawer owns detailed provider evidence, probe timing, warnings and reconciliation data.

Examples:

- **Cloudflare Tunnels** owns Cloudflare control-plane API reachability, Tunnel inventory, Access applications/policies and Service Token inventory correlation.
- **pfSense API** owns REST API reachability, DNS Resolver posture, security-control runtime state and `snort2c` attribution telemetry.
- **TrueNAS** owns the TrueNAS HTTPS/API/runtime evidence.

A Card can be healthy while one subordinate object needs attention. For example, a reachable Cloudflare API with two healthy Tunnels and one inactive legacy Tunnel is **not** an unreachable Cloudflare service.

### Flow is path/dependency context

The TrueNAS Flow is a compact path visualization. It must not duplicate large provider warning blocks or become a second source of truth for service status.

Flow stages may link to the canonical Card that owns their diagnostics. The path may include:

1. **Public DNS** — measured hostname resolution from the current runtime. The UI must not label the provider `Cloudflare DNS` unless provider authority is explicitly observed by the contract.
2. **pfSense WAN ingress** — PF/security controls in the WAN path. The stage links to the pfSense Card.
3. **pfSense DNS / Unbound** — read-only resolver posture, upstream count and TrueNAS-independence evidence. It also links to the pfSense Card.
4. **TrueNAS transport/API stages** — TCP/TLS/HAProxy or direct-LAN/HTTPS/WebSocket/API evidence.

Pi-hole is not inferred from an upstream address. It should be drawn as a specific resolver dependency only after the topology/health contract explicitly attributes that DNS hop to Pi-hole.

## Evidence colors

Colors describe the confidence and outcome of the specific evidence, not a generic severity guess:

| Color | Meaning |
| --- | --- |
| Green | Confirmed healthy / expected observation succeeded |
| Amber | Confirmed attention, degradation, stale evidence or configuration drift |
| Red | Confirmed failure, policy violation or proven security block |
| Gray | Unavailable, not observed, not applicable, or API-dependent control disabled because its authority cannot currently be queried |

A timeout or missing observer evidence should therefore normally be gray/unknown unless another independent signal proves an actual failure.

## Cloudflare model

Cloudflare is deliberately split into independent layers:

1. **Control-plane API reachability** — can the observer authenticate and read the Cloudflare API?
2. **Tunnel lifecycle inventory** — status of each Tunnel (`healthy`, `inactive`, `degraded`, `down`, etc.).
3. **Tunnel Public Hostnames** — per-hostname route inventory (`config.ingress[]` for dashboard-managed Tunnels).
4. **Access applications and policies** — authorization configuration.
5. **Service Token inventory** — whether the configured Access client ID is present in a successfully read inventory.
6. **Live Access edge proof** — anonymous request blocked/challenged vs Service Token request allowed.

`reachable` for the Cloudflare Card describes the read-only control-plane endpoint, not the aggregate lifecycle state of every Tunnel. Individual Tunnel states stay visible inside Service diagnostics.

If the Cloudflare API/control-plane evidence is unavailable or unconfirmed:

- the Cloudflare Card becomes **unknown/gray**, not DOWN solely for that reason;
- per-service **Tunnel**, **Access** and Cloudflare-derived **Policy** controls are gray/disabled;
- live HTTP/TLS and Service Token edge evidence remains independent and can still be shown;
- the UI must not assert that a hostname, Access application, policy or Service Token is absent.

A Service Token is reported as `missing` only when the Service Token inventory call itself succeeded in the current trusted snapshot. A failed/stale inventory produces `correlation unconfirmed`, not a missing-token warning.

For a homogeneous dashboard-managed inventory, `config_src=cloudflare` is implementation detail and is omitted from normal operator text. Management mode is surfaced only when it helps explain mixed/local management or incomplete ingress visibility.

## pfSense model

pfSense is also split into independent layers:

1. **REST API liveness** — lightweight authenticated read-only API evidence.
2. **DNS Resolver posture** — Unbound enabled/running state, forwarding mode/upstream count and resilience relative to TrueNAS.
3. **Security-control runtime state** — PF firewall path plus observed Snort, pfBlockerNG and CrowdSec service state.
4. **`snort2c` attribution telemetry** — whether the currently observed FastAPI egress is present in the Snort/PF block table.

The last two layers must not be conflated. For example:

- `Snort running` means the service runtime was observed running.
- `snort2c telemetry unavailable` means the observer could not currently prove whether the specific FastAPI source is in the block table.

A `ReadTimeout` on `snort2c` therefore does **not** mean Snort, PF or pfBlockerNG is down. It is neutral diagnostic uncertainty unless a separate liveness/runtime check fails.

The Flow displays compact security-control badges with distinct icons and hover details:

- `🧱` pfSense/PF
- `🛡️` Snort
- `🚫` pfBlockerNG
- `👥` CrowdSec

Only a **proven ingress block** stays as a prominent red Flow message. Telemetry unavailable/stale detail belongs in the pfSense Service diagnostics drawer.

## Probe timing and freshness

The Service diagnostics timing grid has a stable field order. Missing values render as `—` rather than removing the field. The one-second UI ticker updates only time-dependent values such as probe age, next due and pending state; it must not rebuild the complete diagnostics DOM every second.

This prevents the visual reordering/flicker that previously occurred when optional fields appeared or disappeared between snapshots.

## Health and filters

`Service health and filters` is operator-controlled and responsive:

- **Collapse / Expand** is always available, not only after the panel becomes sticky;
- desktop keeps the panel bounded and centered;
- mobile bounds expanded height and keeps the compact form small enough not to obscure the service list;
- the **Legend / how to read** summary remains discoverable even in compact mode.

The legend states the ownership rule directly: **Cards = canonical operational state; Flow = path/dependency context.**
