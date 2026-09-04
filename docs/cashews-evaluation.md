# Cashews adoption evaluation

This document evaluates whether `cashews` should replace part of the custom
external-probe resilience stack. It is an engineering assessment, not approval
to migrate production cache state.

## Current baseline

The current health-probe resilience layer deliberately separates concerns:

- process-local L1 cache;
- optional Redis L2 cache;
- outcome-aware success/failure TTLs;
- explicit `current` failure and separate `last_good` evidence;
- stale-last-good projection without hiding the current failure;
- process-local per-key single-flight;
- Redis distributed single-flight with token-safe lock release;
- provider-wide circuit state shared by several probe keys;
- Redis-backed coarse circuit state and a single distributed half-open owner;
- fixed-cardinality metrics and explicit Redis-degraded metadata;
- deterministic unit tests plus real Redis integration coverage.

The main implementation modules currently total roughly 1,178 lines before
their focused tests:

| Module | Approx. lines | Responsibility |
| --- | ---: | --- |
| `external_probe_cache.py` | 478 | cache orchestration and result semantics |
| `external_probe_cache_redis.py` | 85 | Redis envelope/lock primitives |
| `external_probe_cache_types.py` | 46 | cache policy/result contracts |
| `provider_circuit.py` | 437 | provider-wide breaker and half-open ownership |
| `provider_probe_policies.py` | 46 | centralized provider budgets |
| `probe_metrics.py` | 86 | bounded observability |

That size is large enough to justify evaluating a maintained library, but line
count alone must not erase security or degraded-mode semantics.

## What Cashews can replace well

Cashews 7.5 provides several primitives that overlap with this stack:

- memory and Redis backends;
- ordinary TTL caches;
- failover cache;
- soft TTL cache;
- early/background refresh;
- locked execution for cache stampede prevention;
- circuit breaker strategy with half-open support;
- rate-limit primitives;
- Prometheus middleware;
- Redis Cluster/client-side cache options.

The most promising substitutions are therefore:

1. process-local memory caching;
2. ordinary Redis get/set/expiry plumbing;
3. some per-key stampede protection;
4. generic cache metrics;
5. non-security failover caches whose failure semantics are simple.

## Semantic gaps that block a direct replacement

### Current failure must remain visible

For infrastructure diagnostics a failed refresh is itself important evidence.
The application currently exposes both:

```text
current = failed observation
last_good = previous successful observation
```

A failover/soft cache that simply returns the prior successful value can make a
currently failing provider appear healthy. Any Cashews adapter must preserve the
two observations independently and mark stale evidence explicitly.

### The circuit is provider-wide, not function-wide

pfSense deliberately shares one pressure-relief circuit across at least:

```text
pfsense:liveness
pfsense:posture
pfsense:snort2c
```

This protects the appliance when several cache keys become cold together.
Cashews' decorator-oriented circuit breaker cannot be assumed equivalent until a
test proves that several logical keys share one coarse provider circuit and that
the state is consistent across replicas.

### Exactly one distributed half-open probe

The existing breaker coordinates one recovery probe across replicas using Redis
ownership. A candidate replacement must prove the same behavior under
concurrent callers. Allowing each replica one half-open probe would recreate the
recovery stampede the current implementation was designed to prevent.

### Redis degradation is observable

Redis is intentionally best-effort, not a liveness dependency. The current
result metadata can distinguish local fallback from Redis-backed operation.
Cashews suppresses Redis connection errors by default unless configured
otherwise, so using its defaults would hide an operational signal the health
stack currently exposes.

### Serialization is a security boundary

Cashews' Redis backend uses pickle by default and documents use of a secret/hash
to protect serialized objects. The current health cache stores sanitized,
versioned JSON-like envelopes instead.

For shared production health/security evidence, the migration requirement is:

- no default pickle state;
- JSON-safe/versioned payloads;
- schema validation before use;
- no credentials or raw provider responses;
- explicit behavior for incompatible schema versions.

A Cashews experiment may use its JSON serializer only after verifying that the
required envelope types round-trip without weakening validation.

## Decision matrix

| Capability | Current stack | Cashews 7.5 | Migration assessment |
| --- | --- | --- | --- |
| Memory L1 | Yes | Yes | Strong fit |
| Redis L2 | Yes | Yes | Strong fit with serialization constraints |
| TTL policies | Success/failure/stale separately | Yes | Adapter required |
| Per-key stampede protection | Local + Redis | `locked` / early | Promising; benchmark |
| Current failure + last-good | Explicit | Failover/soft favors cached value | Gap |
| Provider-wide cross-key breaker | Yes | Not proven for this model | Blocking gap |
| Distributed single half-open owner | Yes | Not proven | Blocking gap |
| Redis unavailable metadata | Explicit | errors suppressed by default | Adapter/config required |
| Versioned JSON envelope | Yes | pickle default; JSON option limited | Security gap |
| Fixed-cardinality metrics | Yes | Prometheus middleware | Potential simplification |
| Deterministic reset hooks | Yes | Available cache APIs | Must prove test isolation |
| Real Redis tests | Yes | Library has Redis support | Project contract still required |
| HTTP rate limiting | SlowAPI | Cashews has function limits | Do not mix concerns |

## Recommended adoption plan

### Phase 0 — no dependency change

Keep the current production health cache unchanged while SlowAPI, settings,
HTTP-client lifecycle and logging consolidation reduce surrounding debt.

### Phase 1 — isolated technical spike

Add Cashews only to a branch/test dependency context and implement the same
contract for one synthetic provider. The spike must cover:

- Redis healthy;
- Redis unavailable;
- concurrent local callers;
- concurrent simulated replicas;
- fresh success;
- fresh failure after prior success;
- stale-last-good;
- circuit open;
- half-open recovery;
- schema rejection;
- cancellation/deadline behavior.

Measure origin-call count, Redis operations, latency, allocations where
practical, and application-owned lines needed to preserve the contract.

### Phase 2 — low-risk pilot

If the spike succeeds, use Cashews first for a non-security, non-liveness cache
whose semantics are ordinary TTL/failover. Do not begin with `snort2c`,
pfSense posture or TrueNAS health.

### Phase 3 — external-probe adapter

Only if the pilot remains observable and stable, introduce a narrow adapter
behind the existing `ProbeCacheResult` contract. Consumers must not be rewritten
to Cashews decorators directly; preserving the project-owned boundary keeps a
rollback possible.

### Phase 4 — delete custom primitives only after parity

Custom L1/L2/lock code can be removed only after the real-Redis and concurrency
test suites pass against the replacement. Provider-circuit code remains unless
Cashews demonstrably replaces its cross-key and cross-replica semantics.

## Rejection criteria

Reject or limit the migration if any of these remain true:

- current provider failure is hidden by a cached successful value;
- Redis pickle is required for the production envelope;
- Redis failure becomes fatal to health routes;
- provider-wide circuit state must be reimplemented almost entirely around the
  library;
- half-open recovery permits more origin probes than today;
- cache metadata becomes less useful for production diagnosis;
- the adapter plus migration code does not materially reduce custom complexity;
- the dependency adds a second HTTP rate-limiting policy beside SlowAPI.

## Conclusion

Cashews is a credible candidate for reducing generic cache and stampede-control
code, but it is not yet a drop-in replacement for the external-probe resilience
contract. Its highest-value first use is a measured, isolated cache pilot. The
provider-wide circuit breaker and failure-visible stale-last-good semantics are
the two main architectural gates to a broader migration.
