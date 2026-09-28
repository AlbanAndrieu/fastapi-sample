# Cloudflare and Sentry runtime diagnostics

This reference defines how Cloudflare and Sentry evidence is interpreted.
Historical observations and logging incidents belong in
[incidents.md](incidents.md).

## Cloudflare observer

The read-only observer uses `CLOUDFLARE_ACCOUNT_ID` and
`CLOUDFLARE_API_TOKEN`. It never emits provider tokens, Access secrets or DSN
credentials.

For dashboard-managed Tunnels (`config_src=cloudflare`), Cloudflare API data is
authoritative for Public Hostname routing. Reconcile the observed origin
host/port against canonical topology `internalHost`/`internalPort`.

A mismatch is exposure/configuration drift. It does **not** make an otherwise
healthy application DOWN.

Useful bounded provider-level evidence includes:

- Tunnel inventory and connector state;
- Access Applications and reusable policy counts/assignments;
- Service Token inventory and whether the configured client ID is present;
- connector edge colo/version/start time/origin public IP when available.

Provider API timeout, permission failure or incomplete inventory is
**unknown/warning evidence**. It must not automatically mark the workload or
global homelab platform DOWN/degraded.

A live Service Token probe is stronger evidence than inventory alone because it
proves the automated Access path.

## Sentry routing

Telemetry delivery uses this selection:

1. if `SENTRY_LOCAL_DSN` is configured and reachable, use it;
2. otherwise use `SENTRY_DSN`;
3. never derive self-hosted credentials from a SaaS DSN.

Health semantics are deliberately stricter: when `SENTRY_LOCAL_DSN` is
configured, the local endpoint remains the health target even if telemetry falls
back to SaaS. A local outage must not become green because SaaS is reachable.

Typical homelab configuration:

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

Startup logs may expose only sanitized routing metadata: target, scheme, host,
port and project ID. Never log DSN keys/secrets.

HTTPS DSN reachability performs real TLS verification; the internal HTTP DSN does
not use that TLS branch.

## Evidence depth

- HTTP response proves transport/application response only.
- Tunnel inventory proves a route is configured/observed.
- Access policy evidence describes the authorization boundary.
- Service Token live probe proves an automated identity path.
- Topology-origin comparison detects drift.
- Sentry DSN socket reachability proves transport only.
- Sentry ingestion requires a controlled event ID plus downstream confirmation.

Cloudflare and Sentry evidence remain independent from application availability.

## WebSocket timeout correlation

A generic `websocket-client` timeout must not immediately be attributed to
TrueNAS. Correlate its timestamp with integration-specific diagnostics containing
method, sanitized WebSocket URI, TLS/proxy route, phase
(`connect`/`authentication`/`call`), failure stage, exception type and
elapsed time.

Retain the generic Sentry event as transport evidence; tag/context enrichment
should remain sanitized.
