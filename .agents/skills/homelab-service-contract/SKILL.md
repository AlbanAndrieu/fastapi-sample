---
name: homelab-service-contract
description: Detect cross-repository API and semantic drift in the homelab service catalog shared by fastapi-sample and nabla-site-alban. Use when changing homelab catalog fields, service exposure, tunnel URLs, health/sick probes, JSON generation, or the TrueNAS/Nabla service UI.
license: Apache-2.0
role: reviewer
---

# Homelab service contract

## Goal

Keep the homelab service contract compatible across `fastapi-sample` and `AlbanAndrieu/nabla-site-alban`, including behavior that cannot be detected from JSON shape alone.

Treat repository code as the source of truth. Do not copy a permanent field inventory into this skill; derive the active contract from the producer, fixtures/schema, and every consumer.

## Repositories and surfaces

Inspect the local `fastapi-sample` implementation first, especially:

- `nabla/api/homelab_catalog.py`
- `nabla/api/health_checks.py`
- related API routes, Pydantic models, JSON Schema/OpenAPI, tests, and generated artifacts when present

Inspect the current default branch of `AlbanAndrieu/nabla-site-alban` and any PR explicitly involved in the requested change, especially:

- `public/homelab-services.json`
- `public/homelab-services-render.js`
- `app/components/truenas/ServiceGrid.tsx`
- other code referencing catalog fields such as `external`, `tunnelUrl`, internal endpoints, reachability, TLS, or probe state

Use an available GitHub integration/API or a checked-out repository. When reviewing a PR, compare its head with the consumer default branch rather than relying on the PR description alone.

## Review workflow

1. Read the local diff and identify every catalog field or behavior that changes.
2. Read the current producer/consumer implementations in both repositories.
3. Build a field-use matrix showing which component reads, writes, validates, renders, or probes each affected field.
4. Compare JSON shape, types, required/optional status, defaults, aliases, and schema version.
5. Compare semantics separately from shape. Check whether the same value controls clickability, visibility, monitoring, TLS indicators, labels, or network probes consistently in every consumer.
6. Search both repositories for legacy field names and duplicate implementations before declaring a migration complete.
7. Classify the change and state the required migration/tests.

## Drift classification

Use these classes:

- **BREAKING** — field removal/rename without compatibility, type change, required-field change, changed meaning that makes an existing consumer behave incorrectly, or an endpoint/version change without migration.
- **COMPATIBLE** — additive optional field or semantic extension that preserves existing consumers, including a deliberately temporary alias/fallback.
- **SEMANTIC DRIFT** — JSON still parses but two consumers interpret the same data differently. Treat this as a correctness failure even when schemas match.
- **DATA ONLY** — values changed without changing the contract or behavior.

## Exposure and probing invariant

Do not infer public reachability from the presence of `tunnelUrl` alone.

During the current migration, `external` is the preferred exposure-policy field and `reacheableFromOutside` is a legacy alias only when compatibility is intentionally required. Verify this against the current consumer branch before applying it.

When the active contract defines `external: false` as internal-only:

- the public/external UI control must not be clickable;
- public reachability/TLS probes must not run solely because a stale `tunnelUrl` exists;
- monitoring code must explicitly apply the same exposure policy rather than selecting every HTTPS `tunnelUrl`;
- stale external URLs should be reported as data debt and removed when they are no longer meaningful.

If internal monitoring is desired later, model it independently from exposure instead of overloading `external` (for example with an explicit monitoring policy/target).

## Required review output

Return a concise report containing:

1. affected fields and components;
2. compatibility classification;
3. behavioral/UI differences;
4. stale legacy aliases or URLs;
5. required producer and consumer changes;
6. focused contract tests that should be added or updated.

Flag a change as incomplete if the JSON renderer and React/Next.js renderer do not implement the same semantics.

## Target architecture

Prefer evolving toward `fastapi-sample` as the catalog contract owner and producer:

1. define the service model with typed Pydantic models;
2. expose a versioned read-only catalog endpoint and generated JSON Schema/OpenAPI;
3. generate the JSON artifact from the same typed model rather than maintaining a second handwritten contract;
4. let `nabla-site-alban` consume the generated contract at build/deploy time or from a cacheable read-only endpoint;
5. generate or validate TypeScript types from the producer schema;
6. run consumer contract validation in CI so incompatible producer changes fail before deployment.

Keep transport, exposure policy, health monitoring policy, and UI presentation as separate concepts. Avoid making a consumer repository the implicit source of truth for backend monitoring.

## Suggested contract tests

At minimum, cover these cases when the corresponding fields exist:

- externally exposed service with a valid external URL;
- internal-only service that still contains a stale external URL;
- service without an external URL;
- legacy alias during migration;
- conflicting legacy and new fields, where the new field must have deterministic precedence;
- malformed/unsupported URL scheme;
- producer schema version unknown to the consumer.

For each case, assert both serialized contract behavior and consumer behavior (render/probe eligibility), not only successful JSON parsing.
