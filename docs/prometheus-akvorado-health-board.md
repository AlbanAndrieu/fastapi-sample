# Prometheus → FastAPI Cloud: Akvorado scrape visibility

Source of truth for scrapes: `nabla-compose/apps/prometheus/prometheus.yml`.
The jobs `akvorado_inlet` (172.17.0.24:31057) and
`akvorado_outlet` (172.17.0.24:31058) are **internal**.
The frontend never queries these addresses or the Prometheus API directly.

## Read-only snapshot path

1. TrueNAS Prometheus scrapes the Akvorado jobs.
2. A fixed, single Prometheus query supplies bounded exporter data to
   `nabla/api/platform_metrics.py`; raw `up` is a temporary fallback while
   the Compose recording-rule aggregation is deployed.
3. `/api/health-board` returns `platform_metrics.exporter_jobs`.
4. On FastAPI Cloud, the service-probe UI renders these telemetry badges in
   the **public row** without claiming a LAN probe ran in the cloud.
5. Local/homelab mode retains its distinct LAN probe plane.

Scrape UP is not proof that pfSense NetFlow/UDP was received, that Kafka
produced and consumed messages, or that Akvorado inserted ClickHouse rows.

## Production configuration: opt in only

FastAPI Cloud cannot address `172.17.0.24:9090` directly from the
public Internet. `HOMELAB_PROMETHEUS_URL` must be set to an **approved
reachable** endpoint; the endpoint must support read-only
`/api/v1/query` and must be protected by Cloudflare Access.

If using the existing trusted hostname, configure:

- `HOMELAB_PROMETHEUS_URL=https://prometheus.albandrieu.com`
- `HOMELAB_PROMETHEUS_TIMEOUT_SECONDS=3` (bounded, optional)
- `HOMELAB_PROMETHEUS_CF_ACCESS_CLIENT_ID` as a FastAPI Cloud secret
- `HOMELAB_PROMETHEUS_CF_ACCESS_CLIENT_SECRET` as a FastAPI Cloud secret

The two secrets are **optional**, used only as a pair, and only sent to
the exact hostname `prometheus.albandrieu.com` over verified HTTPS
without redirects. Neither appears in the API result or any logs.
Create a Cloudflare Access **Service Auth** policy limited to the
Prometheus application and preferably a **read-only query-only** proxy.
Avoid exposing `/api/v1/admin`, configuration or TSDB endpoints from
the Internet. Never disable Access simply to make the dashboard green.

A configured URL is not proof of reachability. An Access 401/403, an
unreachable private address, a stale snapshot and a missing recording
rule all remain `telemetry_unavailable`/unknown until independently
verified.

## Operator checks

From the workstation connected to the LAN:

```bash
python3 scripts/verify-prometheus-cloud-projection.py --check
```

The command queries the approved LAN origin and the cloud
`/api/health-board` endpoint, optionally passing an existing
`DIAGNOSTICS_ACCESS_KEY` as `X-Diagnostics-Key` (never displayed).
It returns a non-zero status when unauthorized, when either job is
missing, or when the observations disagree.

Look for `akvorado_inlet: scrape_projected_up` and
`akvorado_outlet: scrape_projected_up`, then open
`https://fastapi-sample.fastapicloud.dev/api?q=Akvorado` and check
the Inlet/Outlet cards and their scrape-specific tooltips.
The code must be deployed to FastAPI Cloud before these entries exist
in production. A GitHub PR or a healthy TrueNAS target alone does not
deploy the new projection.

Security and performance: one fixed Prometheus query per board refresh,
no per-card queries, no automatic external discovery, no unauthenticated
direct public metric origin and no LAN reachability inference.
