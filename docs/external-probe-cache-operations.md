# External probe cache operations

This runbook documents the operational contract for the external-provider probe
cache used by TrueNAS, pfSense and Cloudflare diagnostics.

The cache is a pressure-protection layer, not a liveness dependency. Redis is an
optional shared L2: when it is missing or fails, the application must continue
with process-local L1 state, local single-flight and bounded origin probes.

## Data model

The Redis implementation currently uses:

- schema version: `1`;
- probe key prefix: `health:v1:probe:`;
- distributed-lock prefix: `health:v1:lock:`.

Each persisted probe entry is a JSON envelope containing:

- `schema`: the cache schema version;
- `current`: the latest sanitized observation, its success flag and fetch time;
- `last_good`: the most recent successful observation still inside its stale
  evidence window, or `null`;
- optional `circuit_breaker`: coarse circuit metadata only.

Only JSON-serializable sanitized health evidence belongs in this cache. Do not
store credentials, raw provider responses, request headers or secrets.

Redis retention uses the longest configured evidence window for the provider:
the maximum of success TTL, failure TTL and stale TTL. A process-local L1 copy is
also retained for the same maximum evidence window, while its hot bypass window
is capped at five seconds and never exceeds the TTL for the cached outcome.

## Provider policies

The authoritative policy definitions live in
`nabla/api/provider_probe_policies.py`.

| Probe | Success | Failure | Stale | Lock |
| --- | ---: | ---: | ---: | ---: |
| TrueNAS API | 60 s | 120 s | 600 s | 20 s |
| pfSense liveness | 60 s | 120 s | 600 s | 15 s |
| pfSense posture | 60 s | 120 s | 600 s | 15 s |
| pfSense Snort `snort2c` | 60 s | 120 s | 600 s | 15 s |
| Cloudflare tunnels | 90 s | 60 s | 600 s | 15 s |
| Cloudflare exposure | 90 s | 60 s | 600 s | 20 s |

Change these values only in the centralized policy module and keep the contract
tests aligned.

## Schema changes

A schema change must be treated as an explicit invalidation event.

1. Change `SCHEMA_VERSION` when an existing envelope can no longer be safely
   interpreted.
2. Change the versioned Redis key prefixes at the same time
   (`health:vN:probe:` and `health:vN:lock:`).
3. Keep readers strict: an envelope whose `schema` does not equal the current
   version is a cache miss, not partially compatible data.
4. Deploy the new code before deleting old-version keys. Old keys are isolated by
   prefix and expire naturally under their configured TTLs.
5. Never reuse an old lock prefix for a new incompatible schema.

This strategy avoids a coordinated Redis flush during normal schema evolution.

## Targeted invalidation

Application tests and maintenance code use `reset_probe_cache(key, ...)` for a
single probe. With an explicit Redis client, it deletes both the probe entry and
its matching distributed lock after clearing local state.

A reset without a key clears process-local probe state and provider circuits but
does not scan or flush Redis. Production operations should likewise avoid
`FLUSHDB` or broad wildcard deletion unless the Redis database is dedicated and
a full reset is intentionally required.

Prefer natural TTL expiry or deletion of one known versioned key.

## Expected Redis-degraded behavior

When `REDIS_URL` is unset, no shared Redis client is resolved. When a Redis
read, lock or write fails, the failure is treated as degradation rather than an
application-liveness failure.

Expected behavior is:

1. use a fresh L1 result when available;
2. otherwise use retained local evidence when it is still fresh;
3. coordinate same-process callers through the per-key local single-flight lock;
4. consult the provider circuit breaker before starting origin I/O;
5. perform at most the already-bounded origin probe when necessary;
6. retain explicit stale-last-good evidence when the current observation fails.

Cross-replica single-flight and shared L2 reuse are unavailable while Redis is
down, but each process still protects its own origin fan-out. Redis recovery does
not require an application restart.

## Production diagnostics

Use the public operational metrics rather than raw Redis keys as the primary
signal:

- `nabla_external_probe_cache_outcomes_total{outcome=...}`
  - bounded outcomes: `l1_hit`, `redis_hit`, `local_hit`, `miss`,
    `stale`, `redis_degraded`;
- `nabla_external_probe_origin_refreshes_total`;
- `nabla_external_provider_outcomes_total{provider,outcome}`;
- `nabla_external_provider_circuit_state{provider,state}`;
- `nabla_external_probe_timeouts_total{phase}`;
- `nabla_external_probes_in_flight`.

Provider labels are restricted to `truenas`, `pfsense` and `cloudflare`.
Do not add URLs, hostnames, IP addresses, cache keys, exception messages or other
unbounded values as metric labels.

A sustained rise in `redis_degraded` together with normal API liveness means
the fallback is working but shared coordination is unavailable. A simultaneous
rise in origin refreshes, provider failures, open circuits or timeouts warrants
investigation of both Redis and the affected provider.

Debug logs intentionally record only the cache key and exception type for Redis
read/lock/write/release failures; they must not include credentials or raw
provider payloads.

## Validation coverage

Real Redis behavior is exercised in
`tests/integration/test_external_probe_cache_redis.py`, including:

- key expiry;
- rejection of unknown schema versions;
- token-safe distributed lock ownership and release;
- reuse of shared Redis evidence after local state is cleared to simulate another
  replica.

Normal unit tests remain network-disabled unless the dedicated integration
environment explicitly provides `REDIS_INTEGRATION_URL`.
