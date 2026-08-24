---
name: homelab-service-contract
description: Detect cross-repository drift between nabla-compose declarations, TrueNAS runtime observations, fastapi-sample reconciliation/health APIs, and nabla-site-alban presentation.
license: Apache-2.0
role: reviewer
---

# Homelab service contract

## Goal

Keep declared configuration, observed runtime state, operational health and UI presentation compatible without making any one of those concepts stand in for another.

## Ownership model

Treat these boundaries as architectural invariants:

- **`AlbanAndrieu/nabla-compose` owns declared inventory and declared topology.** Service identity, category, source path, runtime binding and architecture relations belong with the Compose code, primarily under `x-nabla`.
- **TrueNAS owns observed runtime facts.** `app.query` reports installed Apps, states, versions, containers, images and ports. Runtime discovery is evidence, never declaration or exposure policy.
- **`fastapi-sample` owns validation, reconciliation, health and API presentation.** It joins declared services to TrueNAS observations and reports drift without rewriting the source declarations.
- **`AlbanAndrieu/nabla-site-alban` owns presentation only.** It must not become an upstream data source for backend monitoring or runtime identity.

Use **Declared != Observed != Healthy** as the mental model:

- declared: what code says should exist;
- observed: what the runtime says exists now;
- healthy: whether a service is operational/reachable according to its monitoring policy.

## Identity and TrueNAS reconciliation

Never match services by display name alone.

For TrueNAS Apps, prefer an explicit `x-nabla.runtime` binding. `provider: truenas-app` must contain at least one of:

- `appId`: exact TrueNAS App identity when known and stable;
- `containerService`: exact Compose service reported by `active_workloads.container_details[].service_name`.

A TrueNAS App may own multiple containers/services, so do not assume one declared service equals one TrueNAS App. Multiple declared services may intentionally bind to distinct `containerService` values inside the same App.

Classify reconciliation explicitly, for example:

- `in_sync`: declaration matches exactly one observed runtime;
- `declared_only`: code declares the service but TrueNAS does not expose a matching runtime;
- `observed_only`: TrueNAS exposes an App not covered by code-owned declarations;
- `binding_conflict`: one declaration matches multiple observed runtimes;
- `runtime_unknown`: TrueNAS cannot be queried;
- `not_observed`: the declared service is logical or intentionally has no TrueNAS binding.

## TrueNAS API invariant

Use the official `truenas_api_client` Python package for TrueNAS middleware access. For application workloads use `app.query`; `service.query` represents TrueNAS system services and is a different inventory.

Keep TrueNAS access read-only for this integration. Never expose credentials, raw API keys or privileged middleware payloads through public API responses.

## Exposure and probing invariant

Do not infer public reachability from ports, portals, DNS names or `tunnelUrl` alone. Runtime discovery must never set `external=true`.

During the migration, `external` remains the preferred exposure-policy field and `reacheableFromOutside` is a legacy input alias only where compatibility is deliberately retained.

When `external: false`:

- external UI controls must not become active merely because a URL exists;
- public probes must not run solely because a stale URL exists;
- internal monitoring must be modeled independently from exposure.

## Catalog generation

Generate declared services and topology from the same `nabla-compose` scan so they cannot drift through independent hand editing. Generated artifacts must be deterministic and CI must fail when checked-in output is stale.

`catalog/services.json` contains code-owned service declarations. `catalog/service-topology.json` contains graph nodes and relations. Keep them separate because consumers need different views, but validate their versions/references together.

During migration, legacy presentation metadata may remain outside the new declared catalog. Do not silently drop it; retire it only after the equivalent code-owned metadata has moved into `x-nabla`.

## Review workflow

1. Read the producer diff in `nabla-compose` and identify changed IDs, runtime bindings and relations.
2. Verify generated services/topology and schemas are synchronized.
3. Inspect `fastapi-sample` models/routes/reconciliation and confirm exact identity semantics.
4. Inspect `nabla-site-alban` consumers and ensure presentation does not reinterpret runtime or exposure fields.
5. Test declared-only, observed-only, exact match, ambiguous match and TrueNAS-unavailable behavior.
6. Search all repositories for legacy aliases or duplicate source-of-truth files before calling a migration complete.

## Compatibility classification

Use these classes:

- **BREAKING** — ID/binding removal, incompatible type/schema change, or semantic change that makes an existing consumer wrong.
- **COMPATIBLE** — additive optional metadata or deliberately retained fallback.
- **SEMANTIC DRIFT** — shapes still parse but producer/runtime/consumer meanings differ; treat as a correctness failure.
- **DATA ONLY** — values change without changing contract semantics.

Keep transport, deployment identity, exposure policy, runtime state, health policy and UI presentation as separate concepts.
