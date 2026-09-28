# Local runtime dependency diagnostic

Use this runbook to validate the TrueNAS-hosted FastAPI observer before resuming
Kubernetes CSI work. The six tracked integrations are TrueNAS, pfSense,
Cloudflare, Prometheus, local Sentry and local Pyroscope.

Historical observations and incidents are kept in
[incidents.md](incidents.md), not here.

## Do not create another probe fan-out

`scripts/diagnose-local-runtime-dependencies.py` reads the cached
`/api/health-board` evidence. It must not contact providers directly.

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

## Normalized evidence contract

For each dependency preserve:

- `configured`;
- `reachable` for transport only;
- `authenticated` only when authentication was actually evaluated;
- `application_ok` and `application_result`;
- `operational_state`;
- `stale` / evidence age;
- `error_stage` and `error_kind`;
- `evidence_complete`.

An HTTP 4xx/5xx proves that the HTTP peer responded; it is not a TCP failure.
Likewise, socket reachability does not prove authentication or application
acceptance.

## Operator entrypoint

```bash
python scripts/diagnose-local-runtime-dependencies.py \
  --url http://172.17.0.24:8091
```

Machine-readable output:

```bash
python scripts/diagnose-local-runtime-dependencies.py \
  --url http://172.17.0.24:8091 \
  --json
```

If `DIAGNOSTICS_ACCESS_KEY` is configured, export it in the shell. The helper
sends it as `X-Diagnostics-Key` and never prints it.

The helper requests one refresh and waits only for the bounded SWR convergence;
it does not bypass provider budgets.

## A/B checks

A workstation result is comparative evidence. It never overwrites the TrueNAS
runtime observation.

### pfSense

Workstation authenticated check:

```bash
curl -sS -o /dev/null \
  -w 'pfsense http=%{http_code} peer=%{remote_ip} tls=%{ssl_verify_result} time=%{time_total}\n' \
  -H "X-API-Key: ${PFSENSE_POSTURE_API_KEY}" \
  -H 'Accept: application/json' \
  https://home.albandrieu.com:10443/api/v2/system/version
```

TrueNAS/container peer and unauthenticated transport check:

```bash
sudo docker exec fastapi-sample getent hosts home.albandrieu.com

sudo docker exec fastapi-sample \
  curl -ksS -o /dev/null \
  -w 'pfsense unauth http=%{http_code} peer=%{remote_ip} time=%{time_total}\n' \
  https://home.albandrieu.com:10443/api/v2/system/version
```

A 401/403 still proves path/HTTP reachability. Do not weaken authentication to
make the diagnostic green.

### Prometheus

```bash
curl -fsS http://172.17.0.24:9090/-/ready

curl -fsS -G http://172.17.0.24:9090/api/v1/query \
  --data-urlencode 'query=up'

sudo docker exec fastapi-sample sh -lc \
  'printf "HOMELAB_PROMETHEUS_URL=%s\n" "${HOMELAB_PROMETHEUS_URL:-<unset>}"'
```

If the variable is unset, fix the authoritative deployment in `nabla-compose`
and redeploy; do not hard-code the homelab address as a library default.

## Required acceptance depth

| Integration | Minimum evidence to close |
| --- | --- |
| TrueNAS | configured + transport + authenticated API operation + expected inventory |
| pfSense | authenticated lightweight REST 2xx from the TrueNAS/LAN observer |
| Cloudflare | authenticated bounded control-plane evidence; provider uncertainty remains warning/unknown |
| Prometheus | configured URL + readiness/query evidence |
| Sentry | synthetic event ID + downstream ingestion proof |
| Pyroscope | readiness 2xx + recent profile query for `service_name=fastapi-sample` |
| Talos follow-up | VM inventory plus independent `talosctl`/`kubectl` cluster proof |

Do not accept Sentry DSN socket reachability as ingestion proof, Pyroscope HTTP
transport as profile evidence, or TrueNAS VM inventory as Kubernetes health.

Open acceptance items are tracked only in
[engineering-roadmap.md](engineering-roadmap.md).
