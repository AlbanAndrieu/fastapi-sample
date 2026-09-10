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
- `reachable` — the intended transport/application endpoint responded;
- `authenticated` — true/false only when the existing evidence actually proves authentication; otherwise `null`;
- `application_result` — the strongest application-level evidence already collected;
- `stale` — whether last-known-good/cache evidence is being served;
- `error_stage` / `error_kind` — the closest known failure phase;
- `evidence_complete` — whether the current probe reaches the depth required for this P0 gate.

Do not infer authentication merely from TCP reachability.

## Current expected gaps

The existing implementation is intentionally expected to report two depth gaps even when the services are up:

- **Sentry** currently uses `probe=dsn_socket`; this proves the selected DSN endpoint is reachable but does not prove API authentication or event ingestion. Final acceptance requires a bounded synthetic event with an event id and downstream evidence.
- **Pyroscope** currently checks `/ready`, `/health` or `/`; this proves service readiness but not that profiling data for `service_name=fastapi-sample` can be queried. Final acceptance requires a bounded read query for the runtime's own profile series.

TrueNAS, pfSense, Cloudflare and Prometheus can already expose stronger application-level evidence through the health-board, but the actual TrueNAS-hosted deployment must be measured before those items are marked complete.

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

## Execution order after the first matrix

Use the first TrueNAS-local report to resolve gaps in this order:

1. TrueNAS API parity and app inventory;
2. pfSense low-impact REST API path;
3. Cloudflare tunnel/Access inventory;
4. Prometheus fixed recording-rule query;
5. Sentry synthetic event path;
6. Pyroscope `fastapi-sample` profile query;
7. local-versus-FastAPI-Cloud A/B report;
8. bounded runtime integration/security/performance baseline;
9. resume TrueNAS NFS + Kubernetes CSI acceptance.
