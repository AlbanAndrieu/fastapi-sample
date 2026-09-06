# Health monitoring environment variables

The health endpoints intentionally keep credentials out of source control. Create the following variables in the target runtime (for example FastAPI Cloud) when the corresponding optional integration should be monitored.

## Runtime observer scope

The deployment runtime is explicit:

```text
FASTAPI_RUNTIME_MODE=homelab
```

Use this only for the TrueNAS production deployment. It produces
`runtime_mode=homelab`, `environment_class=production` and
`observer_scope=trusted_lan`. The FastAPI Cloud deployment remains
`runtime_mode=fastapi_cloud` / `observer_scope=external`, while developer
workstations remain `runtime_mode=local`.

Do not infer this scope from `SICKZ_INTERNAL_NETWORK`, private source
addresses, or hostnames. Those signals describe probe policy or transport, not
deployment identity.

## Endpoint responsibilities

- `/health`: lightweight FastAPI/runtime liveness only; it must not depend on external homelab services.
- `/healthz`: deep dependency diagnostics used by the `/api#health-board` UI.
- `/sickz`: exposure-policy reconciliation. It compares catalog intent (`external`, `tunnelSecure`, Cloudflare Access requirements) with HTTP/TLS, Cloudflare Tunnel/Access and TrueNAS runtime evidence.
- `/api/homelab-services`: validated service inventory and declared exposure settings.
- `/api/homelab-topology`: validated design-time service graph, including nodes and directed relationships.
- `/api/homelab/health`: detailed homelab/platform state, including external and optional internal service probes.

Optional integrations must not make the required/core health red. Missing credentials should be reported as disabled/skipped unless the integration is explicitly enabled and its required credential is missing.

The Homelab endpoints are documented under the `Homelab` section of `/docs` and
in `/openapi.json`. They remain accessible by default. Configure
`DIAGNOSTICS_ACCESS_KEY` to require `X-Diagnostics-Key` or an `Authorization:
Bearer` token for the service catalog, topology, and detailed health endpoints.

Generate an opaque URL-safe value of at least 32 characters; it is compared as
text and must not be decoded by the application:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Store the value in the local untracked `.env.secrets` for local execution and
as a secret environment variable in FastAPI Cloud for production. Authorized
server-side consumers must receive the same value and send either:

```text
X-Diagnostics-Key: <secret>
Authorization: Bearer <secret>
```

Never expose it through browser JavaScript or a `NEXT_PUBLIC_*` variable. A web
application such as `nabla-site-alban` may store it only in its server-side
deployment secrets and proxy requests from a protected server route. Public
pages should instead consume the future redacted public Homelab projection.

## Cloudflare Tunnel and Access APIs

Create:

```text
CLOUDFLARE_ACCOUNT_ID=<Cloudflare account id>
CLOUDFLARE_API_TOKEN=<read-only Cloudflare API token>
```

Use a dedicated token and never reuse a global API key. For complete `/sickz`
security posture, grant only the read permissions required for:

- Cloudflare Tunnel state/configuration;
- `Access: Apps and Policies Read`.

The observer reads Tunnel ingress and Cloudflare Access applications/policies
independently. If the token can read Tunnel configuration but lacks the Access
scope, `/sickz` reports Access protection as unverified rather than assuming a
service is secure.

A Cloudflare Tunnel by itself proves routing through Cloudflare, not Access
authorization. For services whose policy requires Cloudflare Access,
`Bypass + Everyone` or an `Allow` policy that includes Everyone is treated as a
security exception. A host-wide exception is red. A narrowly path-scoped bypass
(for example an incoming webhook endpoint) is orange and should remain as small
as possible. Prefer Cloudflare Service Auth for automated callers when the
integration supports it.

The health probe reads the Cloudflare control plane and reports API reachability separately from tunnel and Access policy state.

## pfSense API

Use separate pfSense identities for posture and Snort/PF security telemetry.
The normal FastAPI Cloud configuration is:

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

When the dedicated URL variables are absent, both identities reuse
`PFSENSE_API_URL`. When their dedicated TLS flags are absent, they reuse
`PFSENSE_API_VERIFY_SSL`. Production completed the split on 2026-09-02 and no
longer defines `PFSENSE_API_KEY`. Runtime code may temporarily keep the old
shared-key name for migration/rollback compatibility, but it is not canonical
configuration and must not be restored merely to satisfy a missing-key diagnostic.

Recommended pfSense service accounts:

- `fastapi-pfsense-posture`: GET only for `/api/v2/system/version`,
  `/api/v2/system/dns`, `/api/v2/status/services`, and
  `/api/v2/services/dns_resolver/settings`;
- `fastapi-pfsense-security`: GET only for
  `/api/v2/diagnostics/table?id=snort2c`.

Do not assign `WebCfg - All pages`, `page-all`, SSH shell access, write/apply,
reboot, command-prompt, DELETE, PATCH, PUT, or POST privileges to either account.
The pfSense user objects must remain enabled: the REST API rejects API-key
authentication when the key owner is marked disabled (`This user cannot login`).
API keys themselves do not grant webConfigurator or SSH authentication.

Keep the REST API globally in read-only mode during normal operation. It may be
temporarily switched out of read-only mode to create/rotate an API key, then
returned immediately to read-only mode. Runtime monitoring requires only GET.

`PFSENSE_API_URL` must use HTTPS when API-key authentication is enabled. Keep TLS verification enabled when the certificate is trusted. If the homelab uses a private/self-signed certificate, the matching `*_VERIFY_SSL=false` switch may be used explicitly, but the transport must still be HTTPS.

The health-board liveness probe intentionally uses the lightweight read-only
version endpoint:

```text
GET /api/v2/system/version
```

Do not use `GET /api/v2/status/system` as the synchronous liveness gate. The
pfSense REST package builds that response from live platform, BIOS, temperature,
CPU/load, mbuf, memory, swap, and filesystem metrics, so a healthy firewall can
exceed a short health-check read timeout. Keep `/api/v2/status/system` for
on-demand or separately cached detailed observability.

FastAPI Cloud currently uses direct reachability for the intentional TrueNAS
`7000` path. The pfSense `10443` WAN probe is diagnostic-only while the
platform lacks a stable application-controlled egress identity: keep it
`trusted_sources_only`, do not chase rotating cloud IPs with permanent
allowlists, and move posture/Snort telemetry to an independent out-of-band
observer. Validate management-port denial from an independent untrusted vantage
point.

## TrueNAS 26 API

Create a dedicated local/API-only TrueNAS service account with the smallest read-only privilege set required by the observer, then create a dedicated API key for that account.

Create:

```text
TRUENAS_URL=https://truenas.albandrieu.com:7000/
TRUENAS_API_USERNAME=<read-only service account>
TRUENAS_API_KEY=<dedicated API key>
TRUENAS_API_VERIFY_SSL=true
```

`TRUENAS_URL` is the single endpoint used by the public HTTP check, optional TCP
probe and authenticated WebSocket adapter. Its production default is
`https://truenas.albandrieu.com:7000/`. Override it only on an internal runtime:

```text
TRUENAS_URL=https://172.17.0.24:7000
```

The adapter also accepts these compatibility fallbacks:

```text
TRUENAS_USERNAME=<fallback username>
TRUENAS_MCP_API_KEY=<fallback API key>
```

Prefer `TRUENAS_API_USERNAME` + `TRUENAS_API_KEY` for the FastAPI runtime so the application credential can be rotated independently of the agent/MCP credential.

TrueNAS 26 uses the JSON-RPC WebSocket API at `/api/current`. The observer currently reads the system version and app inventory only; credentials must never be returned by health endpoints.

`/sickz` also correlates HTTP failures with the observed TrueNAS app state. A
reachable Cloudflare/DNS edge returning `502`, `503`, or `504` while the matching
TrueNAS app is in a failed/down state is reported as a workload failure and the
health board uses a skull icon to distinguish it from a simple exposure-policy
violation.

As with pfSense, do not make the TrueNAS management API public solely to satisfy FastAPI Cloud health checks. Direct checks require network reachability from the runtime to the private TrueNAS address.

## Pydantic Logfire

Create when Logfire telemetry should be enabled:

```text
LOGFIRE_ENABLED=true
LOGFIRE_TOKEN=<project write token>
LOGFIRE_ENVIRONMENT=production
```

Optional custom/self-hosted backend only:

```text
LOGFIRE_BASE_URL=https://<logfire-backend>
```

`LOGFIRE_ENABLED=false` makes the health check intentionally skipped. If Logfire is explicitly enabled but `LOGFIRE_TOKEN` is missing, the optional check reports a configuration failure.

The health check verifies DNS/TCP/TLS connectivity to the configured Logfire ingestion endpoint without sending a synthetic telemetry event. Token contents are never returned.

`LOGFIRE_ENABLE` is accepted as a historical compatibility alias by the health probe, but new deployments should use the canonical `LOGFIRE_ENABLED` variable used by the application instrumentation.

## CI / pytest

External observability integrations should remain disabled in CI unless a test explicitly mocks them. In particular:

```text
LOGFIRE_ENABLED=false
LOGFIRE_TOKEN=
SENTRY_ENABLED=false
SENTRY_DSN=
```

Never put production API keys or write tokens in pull-request CI variables.
