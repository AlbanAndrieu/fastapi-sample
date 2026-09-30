# Incident register

This register groups operational incidents that were previously spread across
roadmaps and diagnostic notes. It intentionally keeps only the evidence required
to recognize a recurrence and points to detailed runbooks for commands and
long-form analysis.

## Triage rule

Always separate these layers before declaring a platform or service DOWN:

1. **network transport** — DNS/TCP/TLS reached the intended peer;
2. **application/control plane** — the HTTP/API operation returned an acceptable
   result;
3. **authentication/authorization** — credentials were actually evaluated;
4. **workload state** — the application or VM/container is running;
5. **dependency evidence** — provider telemetry may be unavailable without the
   workload itself being unavailable.

A timeout, HTTP 404/502, provider API error or missing telemetry is evidence for
one layer only. Do not collapse it into a global outage without corroboration.

## 2026-08-26 — production homelab endpoints returned 500

**Symptom**

- `/api`, `/health`, `/openapi.json`, `/api/homelab-topology`,
  `/api/homelab/runtime` and `/mcp` remained reachable.
- `/healthz`, `/api/homelab-services` and `/api/homelab/health` returned
  HTTP 500.

**Decisive evidence**

A merge retained an obsolete remote-cache implementation after its imports and
state had been removed. The packaged catalog was the intended source.

**Resolution / prevention**

- remove the obsolete remote-cache path;
- exercise the packaged catalog in production smoke tests;
- keep `DEBUG=false` in production so unexpected exceptions do not expose
  tracebacks to public clients.

**Recurrence check**

If only the homelab aggregate endpoints fail while core FastAPI endpoints remain
healthy, inspect catalog/cache initialization before investigating the network.

## 2026-09-02 — FastAPI Cloud ingress blocked by Snort

**Symptom**

FastAPI Cloud could not reach the public TrueNAS HAProxy path on TCP 7000 even
though HAProxy and its TrueNAS backend were healthy.

**Decisive evidence**

- the current cloud egress address was an exact member of PF table `snort2c`;
- WAN capture showed repeated SYN packets without SYN/ACK;
- generated PF rules dropped traffic to/from `snort2c`;
- Snort HTTP Inspect produced GID/SID `120:3` and `120:18` while TCP 7000
  actually carried TLS to HAProxy;
- disabling only Snort WAN and deleting only the observed test IP from
  `snort2c` immediately restored SYN → SYN/ACK → ACK.

This established the causal chain: TLS traffic was classified as clear-text HTTP,
Snort `Block Offenders` inserted the source into `snort2c`, and PF then
silently dropped subsequent connections before TLS started.

**Resolution / prevention**

- remove TCP 7000 from Snort HTTP Inspect clear-text server ports;
- keep block attribution based on exact PF/Snort evidence, not service state;
- change one filtering engine at a time during recurrence testing;
- do not permanently allowlist transient FastAPI Cloud egress addresses;
- distinguish TCP failure from TLS/application failure.

Detailed runbook:
[TrueNAS public ingress diagnostics](truenas-public-ingress.md).

## 2026-09-08 / 2026-09-10 — pfSense WebGUI/API HTTP 502

**Symptom**

Both workstation and TrueNAS/FastAPI vantage points reached pfSense nginx, but
`GET /api/v2/system/version` and WebGUI requests returned native HTTP 502.

**Decisive evidence**

- TCP/TLS transport worked.
- The same 502 was returned before API authentication could be evaluated.
- In the earlier occurrence nginx remained bound while PHP-FPM stopped accepting
  on its socket; CPU pressure and kernel OOM evidence were also observed.
- Unbound failure was concurrent evidence, not automatically the cause.

**Correct interpretation**

```text
pfSense
  network transport       reachable
  API/WebGUI control plane application error (HTTP 502)
  authentication          not evaluated
  Prometheus/exporter     independent evidence
```

**Recovery rule**

Preserve process/socket, CPU/memory/OOM and bounded log evidence before
restarting WebGUI/PHP-FPM. Avoid rebooting the firewall unless the supported
service recovery path fails.

Detailed runbook:
[pfSense webConfigurator 502 recovery](pfsense-webconfigurator-recovery.md).

## 2026-09 — TrueNAS 26.0.0-BETA.3 exposed only CPU0

**Symptom**

TrueNAS application reconciliation became unsafe because the host exposed only
one logical CPU despite an AMD Ryzen 7 7700.

**Decisive evidence**

- `/sys/devices/system/cpu/{possible,present,online}` contained only `0`;
- only `cpu0` existed under the CPU sysfs path;
- SMBIOS still reported 8 cores / 16 threads;
- kernel command line contained no explicit one-CPU limit;
- rollback to TrueNAS 26.0.0-BETA.2 exposed CPUs `0-15`.

**Resolution / prevention**

Treat this as a host/kernel enumeration regression, not a Docker CPU limit.
Remain on the working boot environment and block mass app reconciliation when
host-visible CPU topology is implausible. Do not normalize every application to
one CPU as a workaround.

Active guardrail:
[Homelab security and resilience plan](homelab-security-roadmap.md).

## 2026-09-10 — post-reboot runtime evidence was incomplete

**Symptom**

After TrueNAS reboot, the health board could show misleading or incomplete
service state:

- TrueNAS host/API evidence could diverge;
- Talos VM state required `VM_READ`;
- pfSense returned HTTP 502;
- Prometheus could be `not_configured`;
- a Sentry socket check proved transport only;
- Cloudflare provider uncertainty could be mistaken for workload failure.

**Diagnostic contract**

Use the local TrueNAS-hosted FastAPI runtime as the authoritative homelab
observer and compare workstation results only as A/B evidence. For each provider,
record `configured`, transport, authentication/application acceptance,
observation path and evidence age.

Do not treat:

- Cloudflare timeout/permission/inventory uncertainty as service DOWN;
- Sentry DSN socket reachability as event-ingestion proof;
- TrueNAS VM inventory as Kubernetes/Talos cluster-health proof;
- HTTP 404/502 as a network failure when the peer clearly responded.

Detailed matrix and commands:
[Local runtime dependency convergence](local-runtime-dependency-report.md).

## 2026-09 — observability noise and generic WebSocket timeouts

**Symptom**

Successful demo `/io_task` and `/cpu_task` executions appeared as Sentry
errors, while generic `websocket-client` timeout messages could be mistaken for
proven TrueNAS failures.

**Decisive evidence**

- successful demo endpoints were logged at ERROR instead of INFO;
- `websocket-client` emits generic timeout/close messages without identifying
  the integration that owned the connection;
- TrueNAS diagnostics already expose sanitized phase/stage/timing evidence.

**Resolution / recurrence rule**

- successful demo operations log at INFO; exceptions remain errors;
- retain generic WebSocket timeout events, but correlate them by timestamp with
  integration-specific phase/stage evidence before assigning cause;
- never suppress all `websocket` timeout events globally.

Reference:
[Cloudflare and Sentry runtime diagnostics](cloudflare-sentry-runtime-diagnostics.md).

## Recurrence checklist

For any new incident:

1. record exact date/time and observer vantage point;
2. capture the smallest reproducible request;
3. identify the first failing layer: DNS, TCP, TLS, HTTP/API, auth or workload;
4. preserve bounded logs/resource evidence before restarting infrastructure;
5. compare independent observers when attribution is ambiguous;
6. change one component at a time;
7. update this register only when the incident adds a reusable diagnostic rule.
