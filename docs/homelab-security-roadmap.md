# Homelab security guardrails

This document contains **stable security and resilience rules**, not a second
roadmap. Priorities and open implementation work live only in
[engineering-roadmap.md](engineering-roadmap.md). Dated failures live in
[incidents.md](incidents.md).

## Exposure

- Management surfaces are LAN/private by default.
- Exposure mechanism must be explicit: LAN-only, HAProxy, Cloudflare Tunnel or
  another reviewed path.
- TrueNAS, pfSense, SSH, storage and administration endpoints require explicit
  policy before public exposure.
- Cloudflare control-plane uncertainty is **unknown evidence**, not proof that a
  workload is DOWN.
- Never build firewall allowlists automatically from IP enrichment.

## Health and appliance protection

- `/livez` performs no dependency I/O.
- Required dependencies and optional diagnostics remain distinct.
- Provider probes stay cached, bounded, single-flight and circuit-broken.
- Service-local state remains separate from dependency/effective state.
- Monitor duplication must not overload pfSense or TrueNAS.
- Safe probe rate/concurrency is measured before limits are relaxed.

Operational details:
[external-probe-cache-operations.md](external-probe-cache-operations.md) and
[platform-service-diagnostics-model.md](platform-service-diagnostics-model.md).

## DNS resilience

- TrueNAS Apps failure must not remove basic LAN DNS.
- pfSense/Unbound is the resilient resolver foundation.
- Pi-hole/AdGuard Home are explicit filtering layers, not ambiguous client-side
  resolver fallbacks.
- Resolver behavior is validated with TrueNAS Apps intentionally unavailable.

## Canonical topology and criticality

- Canonical service/node identity and relations come from `nabla-compose`.
- Required/optional dependency semantics propagate into health projection.
- Operational criticality remains distinct from BIA/business criticality.
- Direct catalog cutover removes duplicate local authorities rather than keeping
  parallel schemas.

## UI/security evidence

- Service Cards are the current-state view; topology/flow views add context only.
- Preserve evidence provenance, observer path and freshness.
- Cloudflare, pfSense, TrueNAS, Talos/Kubernetes and Prometheus evidence remain
  independent when they represent different layers.
- Security-framework labels describe control intent, not control effectiveness.

## Host capacity guardrail

Before mass TrueNAS app reconciliation, compare expected hardware with visible
CPU topology and Docker capacity. If host-visible topology is implausible, block
reconciliation and investigate the host/kernel; never normalize all app CPU
limits down to the broken observed capacity.

The 26.0.0-BETA.3 CPU0-only recurrence signature is documented in
[incidents.md](incidents.md#2026-09--truenas-2600-beta3-exposed-only-cpu0).

## Exposure telemetry

- Attribute filtering only from explicit PF/Snort/pfBlocker/CrowdSec evidence.
- Source-IP enrichment is bounded, cached and informational only.
- FastAPI Cloud egress is transient unless the platform documents otherwise.
- Enrichment failure never changes liveness/readiness.
