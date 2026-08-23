# Health monitoring environment variables

The health endpoints intentionally keep credentials out of source control. Create the following variables in the target runtime (for example FastAPI Cloud) when the corresponding optional integration should be monitored.

## Endpoint responsibilities

- `/health`: lightweight FastAPI/runtime liveness only; it must not depend on external homelab services.
- `/healthz`: deep dependency diagnostics used by the `/api#health-board` UI.
- `/api/homelab/health`: detailed homelab/platform state, including external and optional internal service probes.

Optional integrations must not make the required/core health red. Missing credentials should be reported as disabled/skipped unless the integration is explicitly enabled and its required credential is missing.

## Cloudflare Tunnel API

Create:

```text
CLOUDFLARE_ACCOUNT_ID=<Cloudflare account id>
CLOUDFLARE_API_TOKEN=<read-only Cloudflare API token>
```

Use a dedicated token with the minimum permissions needed to read Cloudflare Tunnel state/configuration for the selected account. Do not reuse a global API key.

The health probe reads the Cloudflare Tunnel control plane and reports API reachability separately from tunnel state.

## pfSense API

Create:

```text
PFSENSE_API_URL=https://<pfsense-host>:<https-port>
PFSENSE_API_KEY=<dedicated read-only API key>
PFSENSE_API_VERIFY_SSL=true
```

`PFSENSE_API_URL` must use HTTPS when API-key authentication is enabled. Keep TLS verification enabled when the certificate is trusted. If the homelab uses a private/self-signed certificate, `PFSENSE_API_VERIFY_SSL=false` may be used explicitly, but the transport must still be HTTPS.

The current read-only health probe targets:

```text
GET /api/v2/status/system
```

Do not expose the pfSense management API publicly solely for FastAPI Cloud monitoring. Prefer private connectivity/overlay routing if the FastAPI runtime needs direct access.

## TrueNAS 26 API

Create a dedicated local/API-only TrueNAS service account with the smallest read-only privilege set required by the observer, then create a dedicated API key for that account.

Create:

```text
TRUENAS_URL=https://172.17.0.24
TRUENAS_API_USERNAME=<read-only service account>
TRUENAS_API_KEY=<dedicated API key>
TRUENAS_API_VERIFY_SSL=true
TRUENAS_INTERNAL_HOST=172.17.0.24
TRUENAS_INTERNAL_PORT=443
```

The adapter also accepts these compatibility fallbacks:

```text
TRUENAS_USERNAME=<fallback username>
TRUENAS_MCP_API_KEY=<fallback API key>
```

Prefer `TRUENAS_API_USERNAME` + `TRUENAS_API_KEY` for the FastAPI runtime so the application credential can be rotated independently of the agent/MCP credential.

TrueNAS 26 uses the JSON-RPC WebSocket API at `/api/current`. The observer currently reads the system version and app inventory only; credentials must never be returned by health endpoints.

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
