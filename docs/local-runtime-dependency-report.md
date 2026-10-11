# Local runtime dependency diagnostic

Use this runbook to validate the TrueNAS-hosted FastAPI observer before resuming
Kubernetes CSI work. The tracked integrations include TrueNAS, pfSense, Cloudflare, Prometheus,
local Sentry, local Pyroscope, PostgreSQL, Redis and Gatus (via Prometheus).

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

A post-reboot report must not declare overall evidence complete while the cached board is `pending`, `refreshing` or explicitly stale. Such a snapshot remains incomplete even if individual service rows look healthy. The JSON report exposes `snapshot_fresh` separately from `evidence_gaps` for operator triage.

A TrueNAS API response without an `apps` inventory is **incomplete**, not
proof that the TrueNAS application itself failed. A present empty inventory
remains an application-level failure; confirm the observer's APPS_READ permissions
and runtime payload before changing TrueNAS settings.

A PostgreSQL/Redis TCP connection only establishes transport. Cached component evidence without explicit `application_ok: true` remains incomplete: no database authentication, SQL query, Redis PING or application command success may be inferred from an open port.\n\nAn HTTP 4xx/5xx proves that the HTTP peer responded; it is not a TCP failure.
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

## Post-reboot acceptance

Run from the TrueNAS host after the FastAPI container becomes reachable:

```bash
python3 scripts/diagnose-local-runtime-dependencies.py \
  --url http://172.17.0.24:8091 --wait-seconds 50
# Or, from a checked-out repository with Just:
just truenas-check
# Complete post-reboot acceptance (strict exit status):
just truenas-acceptance
```

Only Python standard library is needed for this diagnostic. It triggers one
bounded cached health-board refresh, not direct provider fan-out. Export
`DIAGNOSTICS_ACCESS_KEY` only if the endpoint requires it; never put secrets
in CLI arguments or logs.

In strict mode (default script invocation or `just truenas-acceptance`), exit
code 0 means all nine evidence contracts are complete, 1 means incomplete or
failed evidence, and 2 means the board cannot be fetched. `just truenas-check`
uses `--report-only`: exit 0 means the report was obtained, **not** that all
integrations are healthy. Missing evidence and real failures still appear in
the matrix and are explained in the follow-up triage lines. A fetch failure
continues to return exit 2. The Sentry and Pyroscope
contracts still require deeper evidence, so a report with those gaps does not
necessarily imply that the runtime is unavailable.

Post-reboot verify PostgreSQL and Redis cached component evidence; check Gatus
availability, series coverage and internal mismatch counts via Prometheus.
Gatus or Prometheus gaps are not grounds for marking public services DOWN.
Use the read-only JSON output (`--json`) for machine inspection, and retain a
dated report when investigating reboot recovery.


## Bounded evidence collection — operator commands (read-only by default)

Run from the authorized TrueNAS shell, not FastAPI Cloud. Collect the board
once; do not loop on pfSense or Cloudflare APIs. Avoid `set -x`, `docker inspect`
full environment dumps, plaintext DSNs, tokens or raw Sentry events in tickets.

```bash
cd /mnt/cpool/compose/nabla-compose
# App state and bounded logs (inspect error category; do not share raw secrets).
sudo docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' |
  grep -E 'NAMES|fastapi|postgres|redis|sentry|gatus|prometheus'
sudo docker inspect --format '{{.Name}} user={{.Config.User}} state={{.State.Status}} exit={{.State.ExitCode}}' gatus
curl -fsS --connect-timeout 2 --max-time 5 http://172.17.0.24:9090/-/ready
curl -fsS --connect-timeout 2 --max-time 5 http://172.17.0.24:8085/health
```

`/health` above is a candidate path, not an asserted Gatus contract: if it
returns 404, inspect the configured endpoint rather than calling the service
healthy or blindly switching paths. Never delete Gatus SQLite history.

To verify application commands *with existing least-privilege identities*,
collect only the sanitized result and duration. Do not pass passwords on CLI
arguments and do not commit credentials.

```bash
# Inside the PostgreSQL container, only when its configured role/database is known:
sudo docker exec postgres sh -c 'pg_isready -q' && echo POSTGRES_ACCEPTING
# pg_isready is readiness only; execute SELECT 1 using an already configured,
# least-privilege application role before publishing an application_ok proof.

# No Redis secret is supplied here. Existing authenticated PING proof must
# come from the application/runtime consumer, not an unauthenticated TCP check.

curl -fsS -G --connect-timeout 2 --max-time 8 \
  http://172.17.0.24:9090/api/v1/query \
  --data-urlencode 'query=up{job=~".*[Gg]atus.*"}'
```

The FastAPI snapshot consumer recognizes optional **cached, sanitized** fields
only: `homelab.components.postgres.application_evidence =
{"kind":"sql_select_1","authenticated":true,"ok":true}`;
Redis uses `kind="redis_ping"`. Sentry requires
`healthz.checks.sentry.ingestion_evidence = {"persisted":true,"fresh":true}`.
These are evidence contracts, **not proof that producers already emit them**;
never inject or fabricate them into a health-board response. The producer must
confirm real authenticated commands/event persistence before these rows become
complete. Keep Gatus separate from public WAN/Cloudflare Access evidence.

## FastAPI outside-in and security diagnostics

```bash
cd /path/to/fastapi-sample  # replace with actual checkout path
python3 scripts/diagnose-local-runtime-dependencies.py \
  --url http://172.17.0.24:8091 --wait-seconds 50 --report-only
# Strict, expected to fail until actual end-to-end evidence exists:
just truenas-acceptance

# Inspect public exposure from a vantage point outside TrueNAS:
curl -sS -o /dev/null -w 'public HTTP=%{http_code} TLS=%{ssl_verify_result}\n' \
  --connect-timeout 3 --max-time 10 \
  https://fastapi-sample.fastapicloud.dev/api
```

For secure diagnostic retention, enable it only in a dedicated
current-user-owned, private directory on a trusted local filesystem.
Never share or commit retained logs verbatim:

```bash
private_dir="$(mktemp -d)"
chmod 700 "$private_dir"
QUALITY_FAILURE_LOG_DIR="$private_dir" just quality
# Inspect locally, redact before sharing; delete securely according to local policy.
```

Catalog-v2 and Synthetic Open Schema generators require the reviewed
`nabla-compose` revision and local schema validation; do not perform a
direct cutover or use a generated schema as proof of outside-in authorization.

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
