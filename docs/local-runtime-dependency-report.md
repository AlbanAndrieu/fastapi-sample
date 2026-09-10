# Local FastAPI runtime dependency convergence

The TrueNAS-hosted FastAPI Sample runtime is the first blocking gate before Kubernetes CSI work resumes. The acceptance target is explicit evidence for six read-only integrations from the runtime that serves `http://172.17.0.24:8091` / `https://sample.albandrieu.com`:

1. TrueNAS API;
2. pfSense API;
3. Cloudflare API;
4. Prometheus API;
5. local Sentry;
6. local Pyroscope.

## Do not add another probe fan-out

The application already collects these signals through the cached health-board pipeline. The operator diagnostic `scripts/diagnose-local-runtime-dependencies.py` therefore reads `/api/health-board` and normalizes existing evidence instead of contacting providers directly.

This preserves the current bounded architecture:

```text
provider probes / runtime inventory
            |
            v
    FastAPI health-board
       stale-while-revalidate
            |
            v
 diagnose-local-runtime-dependencies.py
```

A diagnostic run must not multiply TrueNAS, pfSense, Cloudflare, Prometheus, Sentry or Pyroscope traffic.

## Normalized contract

Each dependency reports:

- `configured` — the required runtime setting/credential is present;
- `reachable` — **transport reachability**. Receiving an HTTP response proves this even when the response is `4xx`/`5xx`;
- `authenticated` — true/false only when the existing evidence actually proves authentication; otherwise `null`;
- `application_ok` — whether the strongest observed application-level operation succeeded;
- `application_result` — the strongest application-level evidence already collected;
- `operational_state` — normalized `ok`, `warning`, `configuration_required`, `unreachable`, `application_error`, or `evidence_incomplete`;
- `stale` — whether last-known-good/cache evidence is being served;
- `error_stage` / `error_kind` — the closest known failure phase;
- `evidence_complete` — whether the current probe reaches the depth required for this P0 gate.

Do not infer authentication merely from TCP reachability. Likewise, do not turn an HTTP `404`/`502` into a transport failure: the server path responded, while application acceptance failed or remains unconfirmed.

## Staging evidence — 2026-09-10

Observed from `http://172.17.0.24:8091` using one fresh health-board refresh:

| Dependency | Transport/config evidence | Current interpretation | Remaining acceptance |
| --- | --- | --- | --- |
| TrueNAS | configured, reachable and authenticated; 96 apps; `direct_lan` | accepted | none for this P0 gate |
| pfSense | `/api/v2/system/version` returned HTTP `502` with `dedicated_posture` | HTTP transport responded, but application result failed; authentication is unproven for the `502` | compare workstation and TrueNAS-container path, then require authenticated `2xx` from staging runtime |
| Cloudflare | API reachable and authenticated, but tunnel inventory empty | warning / status unconfirmed; **not DOWN and not degraded solely for this reason** | verify account/token scope with a bounded on-demand inventory check |
| Prometheus | `configured=false`, `state=not_configured` | deployment configuration gap, not a reachability failure | set `HOMELAB_PROMETHEUS_URL`, redeploy, then require recording-rule evidence |
| Sentry | `dsn_socket` reachable | transport-only evidence | bounded synthetic event id plus downstream ingestion proof |
| Pyroscope | HTTP `404` on `/health` | HTTP transport responded, but readiness was not proven | real readiness `2xx` plus bounded recent profile query for `service_name=fastapi-sample` |

The corresponding open work is tracked in the P0 TrueNAS-local dependency section of `docs/engineering-roadmap.md`. Do not report this convergence task complete while any of those roadmap items remains unresolved.

## Operator usage

From the repository checkout on TrueNAS or another trusted LAN operator host:

```bash
python scripts/diagnose-local-runtime-dependencies.py \
  --url http://172.17.0.24:8091
```

If `DIAGNOSTICS_ACCESS_KEY` is configured, export it in the shell. The helper sends it only as `X-Diagnostics-Key` to the FastAPI health-board and never prints the value.

For machine-readable evidence:

```bash
python scripts/diagnose-local-runtime-dependencies.py \
  --url http://172.17.0.24:8091 \
  --json
```

The helper requests one refresh and polls the FastAPI stale-while-revalidate snapshot until the background refresh converges or the bounded wait expires. It does not bypass the application's probe budgets.

## A/B path checks: workstation versus TrueNAS runtime

Workstation reachability is useful because both pfSense and Prometheus are expected to be reachable from the trusted LAN, but it is a **different observer scope** from the FastAPI container. Compare them rather than using workstation success to overwrite staging-runtime evidence.

### pfSense from the workstation

Use the already-exported dedicated posture key; do not print it:

```bash
curl -sS -o /dev/null \
  -w 'pfsense http=%{http_code} peer=%{remote_ip} tls=%{ssl_verify_result} time=%{time_total}\n' \
  -H "X-API-Key: ${PFSENSE_POSTURE_API_KEY}" \
  -H 'Accept: application/json' \
  https://home.albandrieu.com:10443/api/v2/system/version
```

A `2xx` response proves the workstation path and posture credential work. It does not by itself prove the TrueNAS FastAPI-container path.

On TrueNAS, inspect the container's selected peer without exposing a key:

```bash
sudo docker exec fastapi-sample getent hosts home.albandrieu.com
```

```bash
sudo docker exec fastapi-sample \
  curl -ksS -o /dev/null \
  -w 'pfsense unauth http=%{http_code} peer=%{remote_ip} time=%{time_total}\n' \
  https://home.albandrieu.com:10443/api/v2/system/version
```

An unauthenticated `401`/`403` is still useful transport/path evidence. Do not weaken pfSense authentication merely to make this diagnostic green.

### Prometheus from the workstation

First prove the server itself is ready:

```bash
curl -fsS http://172.17.0.24:9090/-/ready
```

Then prove its query API responds:

```bash
curl -fsS -G http://172.17.0.24:9090/api/v1/query \
  --data-urlencode 'query=up'
```

On TrueNAS, verify the FastAPI container actually received the deployment setting:

```bash
sudo docker exec fastapi-sample sh -lc \
  'printf "HOMELAB_PROMETHEUS_URL=%s\n" "${HOMELAB_PROMETHEUS_URL:-<unset>}"'
```

The URL is non-secret. If it is `<unset>`, fix the authoritative TrueNAS deployment configuration in `nabla-compose`, redeploy FastAPI Sample, and then rerun the health-board diagnostic. Do not hard-code a homelab-specific Prometheus address as an application-library default.

## Current expected depth gaps

Even after pfSense, Cloudflare and Prometheus converge, Sentry and Pyroscope still require deeper application evidence:

- **Sentry** currently uses `probe=dsn_socket`; this proves the selected DSN endpoint is reachable but does not prove API authentication or event ingestion. Final acceptance requires a bounded synthetic event with an event id and downstream evidence.
- **Pyroscope** transport/readiness evidence does not prove that profiling data for `service_name=fastapi-sample` can be queried. Final acceptance requires a bounded read query for the runtime's own profile series.

## Execution order after the first matrix

Resolve gaps in this order:

1. TrueNAS API parity and app inventory — currently accepted;
2. pfSense low-impact REST API path;
3. Prometheus deployment configuration and fixed recording-rule query;
4. Cloudflare tunnel/Access inventory confidence without converting uncertainty into DOWN;
5. Sentry synthetic event path;
6. Pyroscope readiness and `fastapi-sample` profile query;
7. local-versus-FastAPI-Cloud A/B report;
8. bounded runtime integration/security/performance baseline;
9. resume TrueNAS NFS + Kubernetes CSI acceptance.
