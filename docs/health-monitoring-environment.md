# Health monitoring configuration reference

This document defines the **configuration contract** for health and homelab
observers. Recovery procedures and dated failures belong in focused runbooks and
[incidents.md](incidents.md).

Optional integrations must not become core liveness dependencies unless they are
explicitly designed as required.

## Runtime observer scope

Set the runtime identity explicitly:

```text
FASTAPI_RUNTIME_MODE=homelab
```

Use `homelab` only for the trusted TrueNAS production observer. FastAPI Cloud
uses its external runtime mode and developer workstations use local mode.

Do not infer deployment identity from private addresses,
`SICKZ_INTERNAL_NETWORK` or hostnames. Those values describe transport/probe
policy, not the runtime trust boundary.

## Endpoint responsibilities

| Endpoint | Responsibility |
| --- | --- |
| `/health` | lightweight FastAPI/runtime liveness; no homelab dependency I/O |
| `/healthz` | deep dependency diagnostics used by the health board |
| `/sickz` | exposure-policy reconciliation: HTTP/TLS, Cloudflare and runtime evidence |
| `/api/homelab-services` | validated service inventory/exposure intent |
| `/api/homelab-topology` | design-time nodes and directed relationships |
| `/api/homelab/health` | detailed platform state and optional provider probes |

Missing optional credentials are disabled/skipped unless the integration is
explicitly enabled and requires them.

## Diagnostics access key

To protect service inventory, topology and detailed health endpoints, configure:

```text
DIAGNOSTICS_ACCESS_KEY=<opaque URL-safe secret, at least 32 characters>
```

Generate a value locally:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Authorized server-side consumers may send either:

```text
X-Diagnostics-Key: <secret>
Authorization: Bearer <secret>
```

Never expose this value in browser JavaScript or `NEXT_PUBLIC_*`. A public site
must use a protected server-side proxy or the redacted public homelab projection.

## Cloudflare Tunnel and Access

Control-plane observation:

```text
CLOUDFLARE_ACCOUNT_ID=<account id>
CLOUDFLARE_API_TOKEN=<dedicated read-only token>
```

Grant only the read permissions required for Tunnel state/configuration and
Access applications/policies. Tunnel visibility without Access permission means
Access protection is **unverified**, not secure and not workload DOWN.

A Tunnel proves routing, not authorization. Broad `Bypass + Everyone` or
equivalent host-wide access remains a security exception; narrow path-scoped
exceptions must stay explicit.

Optional live Service Auth probe:

```text
CF_ACCESS_CLIENT_ID=<service-token client id>
CF_ACCESS_CLIENT_SECRET=<service-token client secret>
```

The normal edge probe runs anonymously first. Retry with the Service Token only
when Cloudflare Access explicitly blocks the anonymous request. Send these
headers only to the intended `albandrieu.com` host/subdomain and never return
them in diagnostics.

Detailed interpretation:
[Cloudflare and Sentry runtime diagnostics](cloudflare-sentry-runtime-diagnostics.md).

## pfSense API

Use independent identities for posture and Snort/PF attribution:

```text
PFSENSE_API_URL=https://<pfsense-host>:<https-port>
PFSENSE_API_VERIFY_SSL=true

PFSENSE_POSTURE_API_KEY=<posture GET-only key>
PFSENSE_POSTURE_API_URL=https://<pfsense-host>:<https-port>      # optional
PFSENSE_POSTURE_API_VERIFY_SSL=true                              # optional

PFSENSE_SECURITY_API_KEY=<diagnostics-table GET-only key>
PFSENSE_SECURITY_API_URL=https://<pfsense-host>:<https-port>    # optional
PFSENSE_SECURITY_API_VERIFY_SSL=true                             # optional
PFSENSE_SECURITY_PATH_MODE=shared_wan
```

Dedicated URLs/TLS flags inherit the common values when omitted. The canonical
deployment uses only the dedicated posture and security API identities.

Least-privilege accounts:

- posture: GET-only version, DNS, service status and resolver policy required by
  the observer;
- security: GET-only diagnostics-table access for `snort2c`.

Do not grant WebCfg-all, shell, reboot, apply, command, DELETE, PATCH, PUT or POST
privileges. Keep the pfSense REST API globally read-only during normal operation.

API-key transport must use HTTPS. Keep certificate verification enabled when the
certificate is trusted; an explicit internal/self-signed endpoint may opt out
with its matching `*_VERIFY_SSL=false` flag without changing other clients.

Normal synchronous liveness uses:

```text
GET /api/v2/system/version
```

Do not substitute `GET /api/v2/status/system`; that endpoint collects deeper
live platform data and belongs behind on-demand/separate caching.

When security telemetry traverses the same WAN PF/Snort path it diagnoses, keep
`PFSENSE_SECURITY_PATH_MODE=shared_wan`. Such failure is a diagnostic blind
spot, not proof that the table is clear. Use `out_of_band` only after an
independent LAN-side observer exists.

Reference:
[pfSense security observer contract](pfsense-security-observability.md) and
[pfSense 502 recovery](pfsense-webconfigurator-recovery.md).

## TrueNAS API

Configure only the dedicated observer identity:

```text
TRUENAS_URL=https://truenas.albandrieu.com:7000/
TRUENAS_API_USERNAME=fastapi_observer
TRUENAS_API_KEY=<dedicated observer API key>
TRUENAS_API_VERIFY_SSL=true
```

`TRUENAS_URL` is shared by HTTP reachability, optional TCP diagnostics and the
authenticated WebSocket adapter. Keep the hostname even for LAN routing so TLS
SNI/hostname validation remains correct; route it locally to the TrueNAS address
rather than replacing it with a bare IP.

Authentication boundaries are strict:

| Consumer | Identity/secret |
| --- | --- |
| FastAPI observer | `TRUENAS_API_USERNAME` + `TRUENAS_API_KEY` |
| infrastructure tooling | `TRUENAS_INFRA_API_USERNAME` + `TRUENAS_INFRA_API_KEY` in `nabla-compose` |
| TrueNAS MCP | launcher identity + `TRUENAS_MCP_API_KEY` |

The application must not pair infrastructure/MCP credentials with the observer
identity. Historical `TRUENAS_USERNAME` / `TRUENAS_USER` fallbacks are not
canonical.

TrueNAS 26 uses the JSON-RPC WebSocket API at `/api/current`. Validate API-key
shape before transport/authentication so malformed credentials are reported as
configuration errors.

Keep the official TrueNAS client pinned to the **deployed appliance release**;
do not independently advance client/server versions.

Transport and authorization remain distinct:

- constructor/WebSocket failures before auth are transport/handshake failures;
- a code-1008 `You are not allowed to access this resource` can indicate
  `system.general.ui_allowlist` source denial before RBAC;
- `GET /api/versions` proves HTTPS reachability only, not WebSocket permission.

For bridge-networked containers, allow the stable source address TrueNAS
actually observes, preferably a dedicated `/32`, rather than a whole shared
Docker subnet.

Use the application venv when diagnosing from the production container:

```bash
docker exec -i fastapi-sample /code/.venv/bin/python - <<'PY'
import websocket
print(websocket.__version__)
PY
```

Reference:
[local runtime dependency diagnostic](local-runtime-dependency-report.md) and
[TrueNAS public ingress diagnostics](truenas-public-ingress.md).

## Pydantic Logfire

Enable only when telemetry is intentionally configured:

```text
LOGFIRE_ENABLED=true
LOGFIRE_TOKEN=<project write token>
LOGFIRE_ENVIRONMENT=production
LOGFIRE_BASE_URL=https://<custom-backend>   # optional
```

`LOGFIRE_ENABLED=false` means intentionally skipped. If enabled without a
token, report configuration failure.

The health probe verifies DNS/TCP/TLS reachability to the ingestion endpoint; it
does not emit a synthetic telemetry event and never exposes the token.

`LOGFIRE_ENABLE` remains a compatibility alias only. New deployments use
`LOGFIRE_ENABLED`.

## Homelab latency telemetry

`/api/homelab/health` publishes fixed-cardinality observations through:

```text
fastapi_homelab_health_phase_duration_seconds
```

Allowed phase labels remain bounded to the known aggregate phases. Do not add
request-, hostname- or service-specific labels.

Do not set or relax a production p95 target from a single request or sparse
window. Measure p95, sample count and dominant phase under healthy cached and
controlled-degradation windows.

PromQL examples and the safe-probe calibration procedure live in
[external probe cache operations](external-probe-cache-operations.md).

## CI / pytest

Disable external observability unless a test explicitly mocks it:

```text
LOGFIRE_ENABLED=false
LOGFIRE_TOKEN=
SENTRY_ENABLED=false
SENTRY_DSN=
```

Never place production API keys, DSNs or write tokens in pull-request CI
variables.

## Configuration invariants

- explicit runtime identity; never infer trust from an IP alone;
- core liveness independent from optional integrations;
- dedicated least-privilege identities per control plane;
- secrets never returned in health payloads;
- HTTPS/TLS verification stays enabled by default;
- transport, authentication and workload evidence remain separate;
- detailed recovery/history belongs in runbooks/incidents, not this reference.
