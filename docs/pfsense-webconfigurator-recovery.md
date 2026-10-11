# pfSense WebGUI/API 502 — FastAPI observer contract

This path is intentionally retained for historical links from
[incidents.md](incidents.md) and the FastAPI health-board documentation.
**Canonical pfSense appliance operations and recovery** are maintained in
[nabla-compose: pfSense diagnosis/recovery](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/pfsense-diagnose-recover.md).
Do not copy pfSense shell, SSH administration or mutation commands into this
application repository.

## What FastAPI should report

When both WebGUI and `GET /api/v2/system/version` return a native nginx
**HTTP 502**, TCP/TLS/HTTP transport has succeeded, but the
webConfigurator/PHP-FPM control plane has not returned a valid application
response. Authentication might never have been evaluated.

```text
network transport       reachable
pfSense UI/API           HTTP 502 (control-plane failure)
API authentication      unknown; not proven invalid
pfsense_exporter         independent telemetry
Unbound                 independent resolver health
```

Do not turn a 502 into a TCP failure or invalid API-key verdict. Conversely,
HTTP 200/30x for the WebGUI alone does not establish the authenticated REST
control-plane is healthy.

## Application probe safety

- Use the lightweight `/api/v2/system/version` check with one bounded attempt
  per failure window; do not retry a 5xx immediately.
- Share/collapse concurrent checks (cache and single-flight); never run deep
  appliance status collection synchronously from an application liveness path.
- Keep the cloud/remote network timeout classification separate from
  trusted homelab/LAN observation; preserve stale-last-good and
  `status_confirmed=false` when provider evidence is unconfirmed.
- Keep `pfsense_exporter`, Unbound, Gatus and Uptime Kuma evidence separate;
  do not align all polling periods into a probe storm.
- A rejected `PFSENSE_POSTURE_API_KEY` (401) is an authentication failure,
  while an expected 403 from a least-privilege identity can be correct.
  Stop repeated rejected-key attempts to avoid REST Login Protection risk.
- Never expose API key values, session tokens, full PF tables or sensitive
  crash reports in the FastAPI status response or Sentry telemetry.

## Recurrence and closure

See the dated 2026-09 recurrence in [incidents.md](incidents.md) and the
[canonical platform incident](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/incidents/2026-09-08-pfsense-webconfigurator-http-502.md). After the
operator has completed the **nabla-compose** recovery procedure, accept
FastAPI's observer only when the trusted LAN runtime returns authenticated
2xx JSON for the lightweight REST endpoint. A separate pfSense runbook
acceptance checks WebGUI/PHP-FPM, Unbound, exporter, monitor cadence and
bounded pre-restart process/socket/OOM evidence.

Operational recovery, including `scripts/pfsense/diagnose-recover.sh --check`
and explicitly approved `--apply`, belongs **only** in `nabla-compose`.
