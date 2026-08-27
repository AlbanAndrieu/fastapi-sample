# Homelab security and resilience roadmap

This roadmap turns `/sickz`, `/healthz`, the TrueNAS read-only runtime inventory, and the declared Nabla service topology into actionable security and availability controls.

## P0 — Public exposure policy

- **pfSense administration (`10443/tcp`)**: allow only from trusted LAN/VPN administration paths. A successful probe from FastAPI Cloud or another Internet vantage point is a security failure.
- **TrueNAS HTTPS/API (`7000/tcp`)**: currently an intentional direct publication through pfSense HAProxy. The path is `Internet -> pfSense WAN:7000 -> HAProxy TLS termination -> TrueNAS 172.17.0.24:7000 over TLS`. This path does **not** use Cloudflare Tunnel and must remain narrowly scoped to the dedicated HAProxy listener/rule.
- **Target state for `7000/tcp`**: after the broad pfSense Easy Rule is removed, do not leave TCP/7000 open to the whole Internet. Create pfSense aliases for explicitly approved source egress addresses/CIDRs (at minimum the verified FastAPI Cloud production egress address set and the trusted work/office public egress address set) and permit only those aliases to the HAProxy listener. Treat the currently observed FastAPI Cloud source address as evidence to verify, not as a permanent allowlist until FastAPI Cloud egress stability/documentation has been confirmed.
- Prefer named pfSense aliases such as `FASTAPI_CLOUD_EGRESS` and `TRUSTED_WORK_EGRESS` over duplicated literal addresses in firewall rules. This keeps future egress changes auditable without broadening the rule.
- **TrueNAS SSH (`9922/tcp`) and firewall SSH (`22/tcp`)**: external reachability is always a failure.
- Remove broad WAN pass rules such as an Easy Rule that permits arbitrary inbound TCP. Every public listener must have an explicit port/service policy.
- Keep Cloudflare Tunnel evidence distinct from direct HAProxy/Traefik exposure. `tunnelSecure=true` means a Cloudflare-protected exposure is expected; direct exceptions must remain auditable and visible as security debt.

## P0 — Health endpoint reliability

- `/healthz` must not return an unhandled HTTP 500 because a probe implementation and its orchestration disagree on a function signature.
- Keep an explicit regression test for the `probe_name=` contract used by the health orchestrator.
- Optional/deep dependency failures must be represented as structured probe diagnostics (`reachable`, HTTP status, error kind, latency) rather than uncaught exceptions.
- Production deployment remains gated by the full pytest suite and source-size refactoring thresholds; do not relax the `<400` health/Sickz JavaScript threshold to unblock a deployment.

## P1 — DNS architecture and resolver resilience

Current risk: making clients depend directly on Pi-hole or AdGuard Home running as a TrueNAS App turns a TrueNAS/Docker outage into a LAN-wide DNS outage even when routing and Wi-Fi are healthy.

Evaluate and document a resilient policy with these goals:

1. Keep **pfSense/Unbound** as a stable recursive/caching resolver and policy anchor available independently from TrueNAS Apps.
2. Decide whether **Pi-hole**, **AdGuard Home**, or both provide filtering upstream/downstream of Unbound; avoid ambiguous client-side DNS ordering that lets clients bypass filtering unpredictably.
3. If filtering resolvers remain client-facing, deploy at least two independent instances on different failure domains rather than two containers on the same TrueNAS host.
4. Define DHCP DNS advertisements, local-zone ownership, DNSSEC behavior, conditional forwarding, and failover semantics explicitly.
5. Add probes for resolver availability and policy correctness, not only TCP/UDP port reachability.
6. Test failure scenarios: TrueNAS reboot, Docker stopped, Pi-hole stopped, AdGuard stopped, Unbound restart, WAN loss, and DNSSEC/upstream failure.

Target principle: a TrueNAS Apps outage may reduce filtering/telemetry but must not by itself remove basic LAN Internet name resolution.

## P1 — Runtime/topology reconciliation

- Reconcile TrueNAS `app.query` state with `nabla-compose/catalog/services.json` and `service-topology.json`.
- Highlight required dependency violations separately from a container-level `RUNNING` state. For example, a logical service must not be shown healthy when a required database/cache/object-store dependency is stopped.
- Report unmanaged TrueNAS Apps explicitly; do not guess their dependency order until their Compose metadata is represented in the topology catalog.
- Derive restart waves from **required** topology edges before optional observability/exposure edges.

### Next API contract: propagate `required` dependencies

Prepare the health API around three distinct concepts instead of overloading one color/state:

1. `local_state`: direct evidence for the service itself (HTTP/application probe, TrueNAS App/container runtime, internal probe, Cloudflare evidence).
2. `dependency_state`: aggregation of outgoing topology relations whose `strength` is `required`; the relation direction is `source -> target`, so an unhealthy target degrades the source.
3. `effective_state`: the final state consumed by FastAPI UI and `nabla-site-alban` after combining local and dependency evidence.

Add structured fields such as:

```json
{
  "local_state": "ok",
  "dependency_state": "degraded",
  "effective_state": "warn",
  "required_dependencies": ["postgres", "clickhouse", "redis", "minio"],
  "blocked_by": ["postgres", "clickhouse"],
  "dependency_evidence": [
    {"id": "postgres", "state": "fail", "relation": "dependsOn"},
    {"id": "clickhouse", "state": "fail", "relation": "storesIn"}
  ]
}
```

Policy:

- a direct/local failure remains `fail` regardless of dependency state;
- a locally healthy/running service with at least one failed **required** dependency becomes `warn`/degraded unless its own application-level probe also proves functional failure, in which case it is `fail`;
- unknown/stale required dependency evidence must not produce green; use `warn` with explicit uncertainty;
- optional relations never downgrade `effective_state` by themselves;
- evaluate propagation deterministically from a graph snapshot, detect required-edge cycles/SCCs, and surface the cycle instead of recursively looping;
- keep both raw/local state and effective/propagated state in the payload so UIs can explain why a service changed color.

Add contract tests for Langfuse (`postgres`, `clickhouse`, `redis`, `minio`), n8n/PostgreSQL, LiteLLM/Ollama, and OpenWebUI/LiteLLM, including stopped Apps with empty `active_workloads`.

## P1 — UI and topology visualization contract

Use one health/status vocabulary across the FastAPI operations UI and every React Flow diagram in `nabla-site-alban`:

- node fill/border = `effective_state`;
- a small inner/runtime indicator = `local_state` so `RUNNING but degraded` is visible rather than collapsed into one color;
- required edge state = healthy/degraded/failed/unknown based on the target dependency evidence;
- optional edges remain visually secondary and must not turn a node red;
- tooltips/details show `blocked_by`, evidence source, observation age and stale status;
- expose/publish edges must visually distinguish `HAProxy direct`, `Cloudflare Tunnel`, `LAN/VPN only`, and ordinary internal service dependencies;
- keep ports visible for infrastructure edges (`7000`, `10443`, `9922`) instead of hiding them behind host labels;
- avoid browser-side probing overriding server-authoritative FastAPI evidence; browser probing remains fallback only when no usable server evidence exists.

FastAPI should remain lightweight: improve its existing health board/components rather than introducing React solely for React Flow. `nabla-site-alban` owns the richer React Flow views and consumes the same API contract.

## P1 — TrueNAS host capacity guardrail

A host with an AMD Ryzen 7 7700 must not proceed with mass application reconciliation when the operating system exposes only CPU 0. Add an operational check comparing expected hardware inventory with host-visible CPU count and Docker `NCPU`; block or warn before app redeploy when the counts are implausibly low.

Evidence on TrueNAS 26.0.0-BETA.3:

- `/proc/cmdline` contains no `maxcpus=1`, `nr_cpus=1`, or equivalent explicit one-CPU limit;
- `kernel_extra_options` is empty;
- `/sys/devices/system/cpu/{possible,present,online}` all contain only `0`;
- only `/sys/devices/system/cpu/cpu0` exists;
- SMBIOS still reports the AMD Ryzen 7 7700 as 8 enabled cores / 16 threads;
- therefore this is upstream of Docker/cgroup CPU limits: the BETA.3 kernel has only identified/allocated CPU0.

Rollback validation on the previous TrueNAS 26.0.0-BETA.2 boot environment shows CPUs `0-15` online in `lscpu -e`. This makes the one-CPU condition specific to the BETA.3 boot environment on this host and is sufficient to **block the TrueNAS upgrade for now**. Do not normalize application CPU limits down to one CPU as a workaround.

Upgrade policy:

- remain on the previous working boot environment until the BETA.3 CPU enumeration regression is explained/fixed;
- preserve BETA.3 diagnostic evidence for upstream comparison;
- before any future retry, validate host-visible CPU topology, Docker `NCPU`, Apps networking, and representative application startup before making the new boot environment default;
- rotate `PFSENSE_API_KEY` again after the TrueNAS upgrade/recovery work is complete because the current key was changed during troubleshooting.

## P2 — Exposure observability

- Surface the expected/observed state of `10443`, `7000`, `9922`, `4000`, `22`, and other reviewed ports in `/sickz`.
- Include the exposure mechanism (`LAN-only`, `HAProxy direct`, `Cloudflare Tunnel`, `Traefik direct`) in diagnostics rather than inferring it only from the hostname.
- Correlate Cloudflare Tunnel/Access evidence, TrueNAS runtime state, application-level HTTP checks, and pfSense port policy without treating any one signal as authoritative for every service.
