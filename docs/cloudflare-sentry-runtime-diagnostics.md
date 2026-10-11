# Cloudflare / Sentry — FastAPI observer and SDK contracts

This document owns the **application-level** Cloudflare health-board semantics,
the Sentry SDK selection logic and WebSocket log correlation.

The canonical platform-side runbook for Cloudflare Tunnel/Access routes,
policy/service-token testing and **self-hosted Sentry ingestion/recovery** is
[nabla-compose: Cloudflare / Sentry platform diagnostics](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/cloudflare-sentry-platform-diagnostics.md).
Keep environment-specific origin mappings and infrastructure administration
there. Dated application incidents remain in [incidents.md](incidents.md).

## Cloudflare read-only observer

The FastAPI observer uses `CLOUDFLARE_ACCOUNT_ID` and
`CLOUDFLARE_API_TOKEN` read-only. It must never emit provider tokens,
Access Service Token credentials or Sentry DSN keys.

For dashboard-managed Tunnels (`config_src=cloudflare`), compare the
provider-observed Public Hostname origin host/port with generated topology
`internalHost` / `internalPort`. Disagreement is **exposure drift**,
not proof that the underlying workload is DOWN.
`config_src=local` can provide incomplete provider-side ingress data.

- Tunnel/connector inventory, Access Applications/policies and Service Token
  presence are bounded and cached control-plane evidence, not workload health.
- Provider timeout, missing scope or incomplete inventory must yield
  **unknown/warning**, not global platform DOWN/degraded.
- A live Access Service Token check is stronger than inventory alone; it
  proves an automated access path, not health of every origin dependency.
- Keep HTTP/TLS reachability, Access authorization, application readiness and
  topology drift as independent evidence and badges.
- HTTPS diagnostic probes require **TLS 1.2 or newer** and certificate
  verification, except for a separately documented internal transport-only
  test. Do not automatically retry failures or increase provider fan-out.

Operational route inventory, the `nabla-truescale` Tunnel and historical
`2fauth` origin evidence are deliberately documented in
[nabla-compose](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/cloudflare-sentry-platform-diagnostics.md),
not duplicated here.

## Sentry SDK destination selection

Application telemetry delivery uses this order:

1. If `SENTRY_LOCAL_DSN` is configured **and reachable**, send to it.
2. Otherwise use `SENTRY_DSN`, the configured fallback.
3. Never derive local self-hosted credentials from the SaaS DSN.

If local Sentry is configured, the **health-board still measures that local
target**, even when SDK delivery falls back to SaaS. Do not silently show
the local service as GREEN because the cloud fallback succeeded.

Example values with placeholders only:

```env
SENTRY_LOCAL_DSN=http://<local-public-key>@172.17.0.24:9005/<local-project-id>
SENTRY_DSN=https://<cloud-public-key>@<cloud-ingest-host>/<cloud-project-id>
SENTRY_ENVIRONMENT=homelab
SENTRY_TRACES_SAMPLE_RATE=0.1
SENTRY_PROFILES_SAMPLE_RATE=0.0
SENTRY_ERROR_SAMPLE_RATE=1.0
SENTRY_MAX_BREADCRUMBS=50
SENTRY_SHUTDOWN_TIMEOUT=2
```

Sanitized startup logs may include only destination type, scheme, host,
port and project ID. HTTPS DSN checks verify TLS; internal HTTP uses no TLS
handshake. A DSN socket probe establishes **transport only**: a controlled
event ID with downstream confirmation is required to prove ingestion, and
that acceptance belongs to the `nabla-compose` runbook.

## WebSocket error attribution

The generic `websocket-client` message
`Connection timed out - goodbye` proves a transport failure, **not**
a TrueNAS outage by itself. Correlate the timestamp with the adapter's
sanitized method/URI, TLS and proxy path, phase
(`connect`/`authentication`/`call`), exception type, failure stage and
elapsed time. Preserve ERROR severity for genuine timeout events and enrich
tags/context without logging secrets or request payloads.

Cloudflare control-plane uncertainty and Sentry SDK fallback must remain
independent of the application's own availability state.
