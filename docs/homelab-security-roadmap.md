# Homelab security and resilience plan

This is the domain-specific security plan for the homelab integration. The
canonical cross-project priority order remains
[engineering-roadmap.md](engineering-roadmap.md). Incident history is in
[incidents.md](incidents.md).

## P0 — public exposure policy

- Keep management surfaces LAN/private by default.
- Represent exposure mechanism explicitly: LAN-only, HAProxy direct, Cloudflare
  Tunnel or other reviewed path.
- Require explicit policy before exposing TrueNAS, pfSense, SSH, storage or other
  administration endpoints.
- Keep Cloudflare provider/API uncertainty as **unknown evidence**, not automatic
  workload failure.
- Never create firewall allowlists automatically from IP enrichment.

**Acceptance:** expected and observed exposure agree, and a provider telemetry
failure cannot create a false DOWN or false-green security result.

## P0 — health endpoint reliability and appliance protection

- Keep `/livez` dependency-free.
- Keep required dependency checks distinct from optional diagnostics.
- Preserve bounded concurrency, stale-cache behavior, provider circuit breakers
  and aggregate deadlines.
- Measure the safe TrueNAS/pfSense probe envelope before relaxing any rate or
  concurrency limit.
- Ensure monitor duplication cannot overload pfSense WebGUI/API or TrueNAS.
- Keep service-local state separate from dependency/effective state so
  `RUNNING but degraded` remains visible.

Operational detail:
[external-probe-cache-operations.md](external-probe-cache-operations.md) and
[platform-service-diagnostics-model.md](platform-service-diagnostics-model.md).

## P1 — DNS resilience

A TrueNAS Apps outage must not remove basic LAN DNS.

- Keep pfSense/Unbound as the resilient resolver foundation.
- Use Pi-hole/AdGuard Home as explicit filtering layers rather than ambiguous
  client-side resolver ordering.
- Validate resolver behavior with TrueNAS Apps intentionally unavailable.

## P1 — runtime/topology reconciliation

- Consume canonical service/node identity and dependency relations from
  `nabla-compose`.
- Propagate required/optional dependency semantics into the health projection.
- Keep operational criticality separate from BIA/business criticality.
- At direct catalog cutover, remove duplicated local authority files rather than
  maintaining two schemas.

## P1 — UI and security evidence

- Service Cards remain the canonical current-state view.
- Flow/topology views provide dependency/path context, not a competing health
  truth.
- Preserve evidence provenance, observer path and freshness.
- Show Cloudflare, pfSense, TrueNAS, Talos/Kubernetes and Prometheus evidence as
  independent layers where appropriate.
- Keep NIST CSF/security-function navigation descriptive; component presence is
  not evidence of control effectiveness.

## P1 — TrueNAS host capacity guardrail

Before mass application reconciliation, compare expected hardware with
host-visible CPU topology and Docker capacity.

A prior TrueNAS 26.0.0-BETA.3 incident exposed only CPU0 on an AMD Ryzen 7 7700,
while rollback to BETA.2 exposed CPUs 0-15. Treat recurrence as a host/kernel
problem and block reconciliation; do not normalize application CPU limits down
to one CPU.

Incident evidence:
[incidents.md](incidents.md#2026-09--truenas-2600-beta3-exposed-only-cpu0).

## P2 — exposure observability

- Surface expected/observed state for reviewed public/admin ports.
- Attribute filtering only from explicit PF/Snort/pfBlocker/CrowdSec evidence.
- Add bounded cached source-IP enrichment (RDAP/ASN/PTR/provider metadata) as
  informational evidence only.
- Optionally observe FastAPI Cloud egress for correlation, but treat it as
  transient unless the hosting platform documents a stable contract.
- Never let enrichment failure affect liveness/readiness.

## Completed baseline

The following capabilities are already implemented and should not be expanded
back into historical checklists:

- service-first health UI with drill-downs;
- explicit Cloudflare/pfSense/TrueNAS evidence semantics;
- bounded provider timeouts, cache, circuit breakers and concurrency;
- typed runtime/topology/BIA projections at the current contract boundary;
- least-privilege split pfSense posture/security credentials;
- immutable GitHub Action references and local-first quality scopes.

Use Git history and focused tests for implementation detail.
