# Cloudflare and Sentry runtime diagnostics

This document records the read-only diagnostics used by `fastapi-sample` to separate application health from edge/control-plane observability.

## Cloudflare Zero Trust observer

The observer uses the canonical `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` pair. It never mutates Cloudflare state and never emits API tokens, Access Service Token secrets, or DSN credentials.

For a dashboard-managed Cloudflare Tunnel (`config_src=cloudflare`), the API is authoritative for Public Hostname routes. A representative verified homelab observation is:

```text
Tunnel: name=nabla-truescale · status=healthy · config_src=cloudflare
2fauth.albandrieu.com -> http://172.17.0.24:30081
```

The service-level reconciliation compares the observed Cloudflare origin host/port with the canonical topology `internalHost`/`internalPort`. A difference is configuration drift and is rendered as a warning/mismatch in exposure evidence. It does **not** make an otherwise healthy application DOWN.

The cached Cloudflare summary also records bounded control-plane evidence for these API families:

- Tunnel inventory: result/total count and request latency;
- Access Applications: result/total count and request latency;
- Access reusable policies: count, total count, aggregate application assignments and request latency;
- Access Service Tokens: count, enabled count, request latency and a boolean indicating whether the configured `CF_ACCESS_CLIENT_ID` exists in the inventory.

A verified diagnostic run on 2026-09-12 observed 3 tunnels, 68 Access applications, 7 reusable policies and 3 Service Tokens. The `2fauth.albandrieu.com` anonymous request was redirected/blocked by Access while the configured Service Token received HTTP 200. These values are observations, not hard-coded expectations.

Cloudflare API/network/permission failures remain `unknown`/warning evidence. They must not, by themselves, mark the application or the global homelab platform DOWN or degraded.

### Additional useful Cloudflare evidence

The Cloudflare API can also expose cloudflared connector/connection information such as connector count, edge colo, cloudflared version, connection start time and origin public IP. These are useful follow-ups for diagnosing a degraded Tunnel without exposing credentials. They should be sampled at provider level rather than once per service.

Per-application Access policy decisions and path scope are also valuable: a host-wide `bypass`/Everyone policy is materially different from a narrowly scoped webhook exception. Reusable policies additionally expose how many applications use each policy.

## Sentry routing: production versus homelab staging

`fastapi-sample` selects Sentry using a local-first rule:

1. if `SENTRY_LOCAL_DSN` is configured and reachable using its configured transport, use the local target;
2. otherwise use `SENTRY_DSN` (or the repository cloud default);
3. never derive self-hosted credentials from a SaaS DSN.

The intended staging DSN is HTTP because the current internal Sentry listener is plain HTTP on `172.17.0.24:9005`:

```env
SENTRY_LOCAL_DSN=http://<local-public-key>@172.17.0.24:9005/<local-project-id>
```

Production should select the SaaS Sentry DSN. Startup logging emits only sanitized routing metadata (`target`, scheme, host, port and project ID), never the DSN public key or secret material. This makes it possible to confirm from FastAPI Cloud logs whether a deployment selected `cloud` or `local` without opening the Sentry project.

For HTTPS DSNs, the reachability probe performs a real TLS handshake and enforces TLS 1.2 or newer. The local HTTP DSN does not enter this TLS branch.

## Production log interpretation

### `io task` and `cpu task`

These messages came from successful demonstration endpoints `/io_task` and `/cpu_task`. They were previously emitted with `logger.error(...)`, so Sentry's logging integration correctly promoted them to error events even though no failure occurred. Successful executions now log at INFO; real exceptions remain error events.

### `websocket: Connection timed out - goodbye`

This exact message is emitted by the `websocket-client` library when its WebSocket application encounters a timeout and closes without a reconnect path. It is not a custom FastAPI message.

In this repository the TrueNAS API adapter is the primary `websocket-client` consumer through `truenas_api_client`. The adapter already emits integration-specific diagnostics containing the method, sanitized WebSocket URI, TLS verification setting, proxy route, phase (`connect`, `authentication`, `call`), classified failure stage, exception type and elapsed time. Correlate those warnings by timestamp with a generic `websocket` timeout before concluding that the timeout was TrueNAS.

Sentry events from logger `websocket` containing a timeout are retained rather than globally suppressed. `before_send` adds non-secret tags/context identifying `websocket-client` and the transport-timeout stage, with a hint to correlate the event with the integration-specific TrueNAS diagnostic. This preserves the production signal while making the issue actionable.

The application cannot prove from the DSN socket probe alone that a particular event has been stored by Sentry. Confirmation of an individual event still requires querying the selected Sentry project or generating a controlled event and locating its event ID. The runtime logs and sanitized destination metadata do establish which Sentry intake/project the deployment selected.

## Operator semantics

Cloudflare, Sentry, TrueNAS and HTTP evidence are independent layers:

- HTTP 2xx/3xx proves application transport response;
- Cloudflare Tunnel evidence proves a route is configured/observed;
- Access policy evidence describes the authorization boundary;
- a Service Token live probe proves the automated identity path works;
- topology-origin comparison detects configuration drift;
- provider API timeout/permission failures mean “unverified”, not service DOWN;
- Sentry transport health describes telemetry delivery, not application availability.
