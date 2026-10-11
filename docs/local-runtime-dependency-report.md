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

## Workstation feedback and local-first test execution — 2026-10-11

Current workstation measurements: Gatus HTTP 200, Prometheus HTTP 200,
Pyroscope **readiness HTTP 200** (recovered from earlier 503). A cached FastAPI
row of `reachable` only proves transport; if Gatus remains `unknown` or
Pyroscope remains `evidence_incomplete`, this is a difference in the
**depth/source of evidence**, not necessarily a live outage. The wrapper
now prints a dynamic, separately sourced readiness statement and does not
repeat historical 503 warnings when the current response is 200.

The local host Python selected by mise may have no pytest distribution. Use
the repository's **uv-managed** test runner instead of `python3 -m pytest`:

```bash
# Workstation, from fastapi-sample:
just test-runtime-evidence
# Equivalent targeted runner:
bash scripts/run-pytest-compact.sh \
  tests/unit/test_truenas_runtime_evidence_wrapper.py \
  tests/unit/test_local_runtime_dependency_report.py
```

The runner calls `uv run --no-sync pytest`. If the locked dependencies are
not already installed, run `uv sync --frozen` from the checkout while
dependency access is available, or `UV_OFFLINE=true uv sync --frozen --offline`
with an already populated cache. Do not install pytest globally just to
run repository tests.

## Operational division of responsibility

`fastapi-sample` checks **basic service reachability**, not full
administrative recovery of every TrueNAS app. The portable wrapper defaults
to `--basic` evidence and reports source perspective; `--detail` prints the
cached strict evidence gaps without failing, and `--strict` retains the
full nine-dependency acceptance gate. Basic mode returning zero only means
the board was read; individual unreachable/unknown rows remain visible.

```bash
# From existing fastapi-sample checkout on workstation; no TrueNAS checkout needed.
bash scripts/truenas-runtime-evidence.sh --vantage workstation
bash scripts/truenas-runtime-evidence.sh --vantage workstation --detail
# Optional strict full acceptance (intentionally may exit 1):
bash scripts/truenas-runtime-evidence.sh --vantage workstation --strict
```

The workstation's `postgres` and `redis` Docker containers are reported
under a distinctly labeled **local** heading and must not become health
evidence for TrueNAS. Pyroscope readiness and Gatus are checked against the
TrueNAS IP. If Pyroscope recently recovered, HTTP 503 may represent a
remaining readiness failure or timing drift; confirm with a new bounded check.

For deeper diagnostics, run these **in the existing nabla-compose checkout on
TrueNAS when warranted**, not from the fastapi-sample workstation script:

```bash
cd /mnt/cpool/compose/nabla-compose
python3 scripts/truenas/diagnose-fastapi-integrations.py --help
bash scripts/truenas/diagnose-sentry.sh --check
bash scripts/truenas/diagnose-gatus.sh
bash scripts/truenas/diagnose-pyroscope.sh
```

The `nabla-compose` scripts are the authoritative service-level recovery
diagnostics. Do not infer authenticated SQL/Redis operations, Sentry event
ingestion, Gatus monitoring history or Pyroscope profile ingestion from a
simple HTTP 200/TCP response.

## Dual-vantage behavior (2026-10-11)

`scripts/truenas-runtime-evidence.sh` is designed for both the workstation and
TrueNAS. Automatic host selection recognizes hostname `truenas`; otherwise it
defaults conservatively to **workstation** and does **not** inspect local
Docker containers as if they belonged to TrueNAS. Override explicitly if
the TrueNAS hostname differs:

```bash
# Existing fastapi-sample checkout on workstation:
bash scripts/truenas-runtime-evidence.sh --vantage workstation
# Existing fastapi-sample checkout on TrueNAS:
bash scripts/truenas-runtime-evidence.sh --vantage truenas
# Strict evidence acceptance from either vantage:
bash scripts/truenas-runtime-evidence.sh --vantage workstation --strict
```

The HTTP tests always target `172.17.0.24`; the FastAPI health-board itself
is served by the TrueNAS observer. Workstation Docker and its independently
running PostgreSQL/Redis are **not** TrueNAS application proof. On TrueNAS,
Docker metadata is collected only when the Docker endpoint/context has not been
overridden. Remote containers are not inspected via an implicit SSH tunnel.

Observed from workstation: Gatus HTTP 200, Prometheus readiness 200, and
Pyroscope readiness HTTP 503 (under repair); do not interpret this as the
workstation's similarly named containers. TrueNAS PostgreSQL readiness was
confirmed independently with `docker exec ix-postgres-postgres-1 pg_isready`.

## Locate the right checkout before running commands

The `docs/local-first-roadmap-consolidation` branch, `just truenas-check`
and `scripts/diagnose-local-runtime-dependencies.py` belong to
**AlbanAndrieu/fastapi-sample**, not `nabla-compose`. When the shell is in
`/mnt/cpool/compose/nabla-compose`, `git pull`, `python3 scripts/...`
and `just truenas-acceptance` will address the **wrong repository**.

```bash
pwd
git remote -v
# Search likely checkout locations without scanning ZFS datasets indiscriminately:
find /mnt/cpool/compose /home/albandrieu -maxdepth 5 \
  -path '*/scripts/diagnose-local-runtime-dependencies.py' -print 2>/dev/null
# cd to the directory ABOVE scripts/ in the result; verify:
git remote get-url origin
git branch --show-current
git fetch origin docs/local-first-roadmap-consolidation
git switch docs/local-first-roadmap-consolidation
git pull --ff-only origin docs/local-first-roadmap-consolidation

# Run safely even if the shell later changes directory:
bash ./scripts/truenas-runtime-evidence.sh
just truenas-evidence
just truenas-evidence-strict
```

If no existing checkout is found, clone `AlbanAndrieu/fastapi-sample` to
an explicitly chosen workspace when network access permits; do not run
FastAPI-specific commands from the `nabla-compose` tree.

The portable wrapper checks the cached health-board, bounded Docker status
and three HTTP endpoints. It is **not** a substitute for authenticated
PostgreSQL `SELECT 1`, Redis `PING`, Sentry ingestion, or Gatus history
persistence. Actual PostgreSQL container:
`ix-postgres-postgres-1`; the observed `pg_isready` result on 2026-10-11
was **accepting connections**, not authenticated SQL acceptance.

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


## Confirmed runtime evidence — 2026-10-11

From the operator's TrueNAS observation:

- **TrueNAS:** cached authenticated inventory is now `ok`.
- **Gatus:** Docker container `gatus` is running, HTTP `:8085/` returned
  **200**, and Prometheus `up{job="gatus"} == 1`. This establishes
  reachability and scrape availability, **not** persisted history or that the
  FastAPI cached Gatus comparison is populated. No reboot/redeploy is warranted
  solely from the outdated Gatus row.
- **PostgreSQL:** the actual main container is
  `ix-postgres-postgres-1`, not `postgres`. Its Docker health is good;
  `pg_isready` and authenticated `SELECT 1` are separate checks.
- **Redis:** the standalone `redis` container is healthy; application
  authenticated PING evidence is still missing from the FastAPI board.
- **Sentry:** NGINX, web, consumers and Snuba are running and mostly healthy;
  the recent-event persistence contract remains independent of container health.
- **Pyroscope:** Prometheus reported `up{job="pyroscope"} = 0`, matching
  missing readiness. Investigate it independently, with no unreviewed UID/ACL
  changes.
- **HTTP policy checks:** pfSense anonymous 401 and Cloudflare Access 302
  are consistent with access being denied or redirected, not with a confirmed
  authenticated API pass. TrueNAS `/api/current` returned 400 and the
  production `/api` route returned 404; neither is by itself proof of a
  backend outage. Use an endpoint with a documented successful response.
- **Independent quality issue:** `nabla-compose` reported one failure in
  `tests/test_gatus_diagnostic_contract.py::test_diagnostic_does_not_leak_raw_logs`
  (220 passed); that is **not** the FastAPI runtime dependency script and
  must be fixed in the owning repository.

Use `--color auto|always|never` on the FastAPI diagnostic: auto emits ANSI
only to a compatible terminal without `NO_COLOR`; JSON output is not
colorized. The icons do **not** alter the strict acceptance exit code.

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
sudo docker exec ix-postgres-postgres-1 pg_isready -q && echo POSTGRES_ACCEPTING
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

## Cross-repository acceptance matrix — PR #335 / nabla-compose PR #253

This separates the observed service state from deep coverage/permissions.
It is based on operator evidence dated 2026-10-11, **not** a fresh live audit.

| Service | Observed state | Available evidence | Missing evidence / likely explanation | Owner / acceptance |
| --- | --- | --- | --- | --- |
| TrueNAS | functional | authenticated API inventory, apps visible | guest Kubernetes and reboot evidence are independent | FastAPI keeps cached read-only inventory; nabla-compose proves cluster/reboot |
| pfSense | HTTP reachable, anonymous 401 | TCP/HTTPS + expected unauthorized API response | authenticated dedicated observer `system.version` 2xx not propagated, possible permissions/snapshot mismatch | FastAPI preserves auth=unknown; nabla-compose tests observer key/least privilege |
| Sentry | core containers healthy | NGINX/web/consumers; DSN socket | a fresh persisted synthetic event cannot be inferred from TCP | FastAPI basic reachable; nabla-compose `diagnose-sentry.sh --check` + E2E event |
| PostgreSQL | healthy | TrueNAS `pg_isready` accepting, :5432 reachable | authenticated SQL proof absent; exporter 9187 not running (separate monitoring coverage) | FastAPI basic reachable; nabla-compose adds approved SQL evidence/exporter only if needed |
| Redis | healthy | TrueNAS container + TCP reachability | authenticated PING missing; workstation Redis is separate | FastAPI basic reachable; nabla-compose consumer-level check |
| Gatus | HTTP 200, Prometheus up=1 previously | direct TrueNAS :8085, scrape up | cached synthetic series missing or stale; `gatus_not_observed` and 11 missing IDs indicate missing coverage, **not** downtime | FastAPI reports missing IDs from internal comparison; nabla-compose PR #253 reconciles catalog vs generated Gatus monitors/metric labels |
| Pyroscope | readiness recovered | /, /metrics and /ready HTTP 200 on workstation; corrected persistent store | recent `service_name=fastapi-sample` ingestion unverified | FastAPI basic ready; nabla-compose `diagnose-pyroscope.sh` and profile proof |

For Gatus, `missing_gatus_ids` is now included by
`compare_internal_probe_evidence` and in the normalized FastAPI report **when
the running backend actually exposes the new field**. Before deployment or
without actual `internal_services` and Gatus metric labels, the exact 11 IDs
cannot be safely reconstructed from the count. Inspect the JSON field and
compare each ID against `nabla-compose/catalog/service-topology.json`, generated
Gatus monitors and Prometheus label normalization. No missing ID is
automatically classified `DOWN`.

Distinguish: service business state, network reachability, auth privileges,
observation freshness, source-of-evidence, generated monitor coverage and
deep end-to-end acceptance. A missing exporter (PostgreSQL 9187), a missing
Gatus series or a cached `evidence_incomplete` state does not downgrade a
confirmed functioning service. Never grant TrueNAS administrator privileges
to make a monitoring check green.

## Gatus Prometheus fallback — 2026-10-11 (PR #335)

FastAPI previously consumed only `nabla:telemetry:gatus_up`; a live
`up{job="gatus"}=1` could coexist with `gatus_not_observed` when
the recording rule was absent. The existing *bounded combined Prometheus
query* now includes `up{job="gatus"}` as a fallback **only when the
recording rule has no value**. The result includes `gatus_source`
(`recording_rule`, `raw_prometheus_up`, or `unavailable`).
Recording-rule evidence takes precedence if both exist.

The fallback proves Prometheus can scrape Gatus; it **does not** fabricate
`nabla_service_id` labels, service counts, probe history or missing monitor
coverage. The comparison and delegation still block with zero observed
internal service metrics. From the running observer after deployment, inspect
`internal_probe_comparison.missing_gatus_ids` to identify the actual 11 missing
services and compare them against the generated Gatus monitors in
`nabla-compose`. Before deployment, exact IDs cannot be inferred from a
count of 11. The external cloud observer stays independent from internal Gatus.

Workstation validation, after pulling this PR branch into the workstation
checkout:

```bash
just test-runtime-evidence
# Equivalent:
bash scripts/run-pytest-compact.sh \
  tests/unit/test_local_runtime_dependency_report.py \
  tests/unit/test_synthetic_probe_comparison.py \
  tests/unit/test_platform_metrics.py
```

`nabla-compose` PR #253 owns the generated Gatus configuration and
Prometheus recording-rule provisioning; `fastapi-sample` PR #335 owns only
bounded collection, classification and diagnostics.

## Gatus gap classification — follow-up to PR #253

The diagnostic now outputs `missing_gatus_reasons` alongside
`missing_gatus_ids`. Each recorded internal service without a matching
Prometheus metric is classified as:

- `no_labeled_service_metrics`: no `nabla_service_id` series for the
  direct service ID; check the canonical service ID, generated Gatus monitor,
  applied Gatus config and Prometheus relabeling.
- `no_valid_comparable_probe`: the ID is present, but no valid TCP, HTTP
  or HTTPS success sample is available; check protocol/metric type, scrape
  lag and rule calculation.

These are **coverage diagnoses, not failure states**. The generator in
`nabla-compose` creates `apps/gatus/config/config.yml` and populates
`nabla_service_id` in endpoint labels. The FastAPI comparison must not
confuse a missing label or unsupported PING-only monitor with a service
outage. The actual list of 11 IDs is still contingent on a runtime snapshot
populated with the newly exposed fields. Preserve the PR #253 generator
as source of authority, and keep FastAPI's outside-in checks unchanged.

## Canonical ID deduplication (PR #335 follow-up)

The Gatus coverage comparator now counts each internal canonical service ID
at most once, even if an observer inventory contains repeated rows. This
prevents duplicate `missing_gatus` counts, misleading mismatch totals and
duplicate identifiers. The first eligible `ok`/`fail` observation for a
service ID is used; inconsistent duplicate observations require source data
reconciliation rather than an inferred service failure.

Validation is included in
`tests/unit/test_synthetic_probe_comparison.py::test_duplicate_internal_ids_are_counted_once`.
A complete local quality gate was not run in the authoring environment because
the GitHub host was unavailable via DNS; do not infer a passing gate from
published commits.

## Inconsistent duplicate evidence (PR #335)

Duplicate rows carrying the same canonical ID and the same direct result
are deduplicated. Rows with **contradictory** direct `ok` / `fail` results
are now excluded from transport comparison, reported in
`conflicting_direct_ids`, and block delegation with
`conflicting_direct_observations`. They are not counted as Gatus missing
or as failed services. The source observer must resolve these conflicting
samples before a delegated probe can be accepted. Existing externally
observed probes remain unaffected.

The authoring container cannot resolve `github.com`; therefore no
local pytest or full quality gate result is claimed on the new HEAD.

## Synthetic metrics unobserved versus genuine coverage gaps

The comparator now refuses to claim missing Gatus monitors when
`platform_metrics.synthetic_probes.state` is not `observed` or the
service metric map is missing. It reports `state=unavailable` with
`reason=synthetic_metrics_not_observed`, preserves external probes,
and does **not** populate `missing_gatus_ids` by guessing. Delegation
continues to block on `gatus_not_observed` and
`no_internal_gatus_evidence`. Only an *observed* service-metric inventory
may be compared to the canonical internal service list. The separate
`up{job="gatus"}` fallback proves scrape reachability, not the
existence of named service monitors.

This prevents temporary missing recording-rule output or a Prometheus
query failure from being misreported as 11 missing configured Gatus
monitors. After observability recovers, compare the actual IDs with
`nabla-compose` PR #253's generated Gatus config.
