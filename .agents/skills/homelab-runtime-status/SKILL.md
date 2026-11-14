---
name: homelab-runtime-status
description: >-
  Validate declared, observed, healthy and exposed homelab service status from
  an explicitly capable workstation; isolate Codex from private LAN.
---
# Homelab runtime status (on demand)

**Capability gate:** read `AGENTS.md` and [the profile runbook](../../../docs/agent-execution-profiles.md). `just agent-context truenas` is read-only and never runs probes. On an authorized workstation use `just agent-diagnostics workstation runtime` for bounded read-only evidence. On Codex/CI run `just agent-diagnostics isolated runtime` for L1 only and report runtime **NOT_RUN**. Never assume the agent can access 172.17.0.0/24, Docker, pfSense, Vault or Cloudflare credentials.

## Source separation

| Evidence | Read model | Meaning |
| --- | --- | --- |
| Declared | Compose Backstage V2 `catalog/generated/entities.json` / `/api/site/catalog/v2` | Desired entityRef, exposure and runtime binding |
| Reconciled | `/api/homelab/status` | `in_sync`, `declared_only`, `observed_only`, `binding_conflict`, `runtime_unknown`, `not_observed` |
| Runtime | `/api/homelab/runtime` | TrueNAS App state (not standalone Docker Compose by default) |
| Health | `/api/homelab/health`, `/healthz`, health-board | Actual functional probe evidence, not an App RUNNING state |
| Topology | `/api/homelab-topology` | Declared dependencies, not measured reachability |
| Exposure | `/sickz` | External vantage/policy; reachable private target may be a finding |

**Never equate** Declared ≠ Observed ≠ Healthy ≠ Externally reachable. `DENIED`, `STALE`, `NOT_RUN`, `NO_SAMPLE` ≠ `DOWN`. Report observer, checked_at, catalogRevision, probe age and the identity used to join observations. A Cloud HTTP 403 is not proof that the TrueNAS origin is down.

## Diagnostic sequence (workstation only)

1. Select **one** scope: `just agent-diagnostics workstation dns`, `metrics`, or `runtime`. These delegate to the existing read-only collectors, not a new fan-out.
2. If the result is inconclusive, compare one affected service's V2 entityRef, `x-nabla.runtime` binding and the appropriate runtime evidence. Do not match by display name alone.
3. Check direct application health before relying on container state, Gatus or TCP. Verify credentials and HTTP semantics without logging secrets.
4. Before/after a migration, compare runtime, persistent data, dependencies, auth and exposure on known SHAs; document any TrueNAS Apps observer blind spot for Compose workloads.
5. Record dated evidence and unresolved gaps in `docs/engineering-roadmap.md`; upstream mutations belong to `nabla-compose`, not FastAPI.

**Safety:** read-only status work never invokes Docker restart/exec, database mutation, pfSense rules or TrueNAS upgrades. Local Docker is explicitly labelled *workstation evidence*, not TrueNAS evidence. Never bypass Cloudflare Access.

## Migration-specific checks

For NPMplus cutover or any destructive migration, first apply the [archived detailed acceptance checklist](../../../docs/archive/2026-11-14-homelab-runtime-status-before-profiles.md) and current Compose runbook. Do not stop the old proxy or claim persistent storage validated from an HTTP response alone.

## Completion gate

An agent must not declare a migration, remediation, diagnostic or validation complete while a known residual, deferred verification or cross-repo follow-up is absent from `docs/engineering-roadmap.md`. Record the next acceptance proof; container RUNNING, HTTP 200, an API denial or a green dashboard alone is insufficient.
