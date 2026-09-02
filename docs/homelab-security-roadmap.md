# Homelab security and resilience roadmap

This roadmap turns `/sickz`, `/healthz`, the TrueNAS read-only runtime inventory, and the declared Nabla service topology into actionable security and availability controls.

## P0 — Public exposure policy

- **pfSense administration/API (`10443/tcp`)**: FastAPI Cloud currently requires this listener for the dedicated read-only posture and Snort/PF observers. Treat it as `trusted_sources_only`: the production FastAPI Cloud runtime and explicitly approved administration sources are expected to reach it, while unrelated Internet origins must remain denied.
- **TrueNAS HTTPS/API (`7000/tcp`)**: currently an intentional direct publication through pfSense HAProxy. The path is `Internet -> pfSense WAN:7000 -> HAProxy TLS termination -> TLS re-encryption -> TrueNAS 172.17.0.24:7000`. This path does **not** use Cloudflare Tunnel and must remain narrowly scoped to the dedicated HAProxy listener/rule.
- **Source-identity constraint**: the current FastAPI Cloud deployment does not expose a user-controlled static egress gateway or outbound tunnel. Observed cloud source IPs are transient diagnostic evidence, not a stable workload identity. Do not automatically populate `FASTAPI_CLOUD_EGRESS`, allow an entire AWS allocation, or convert one observed address into a permanent firewall/Snort pass-list entry.
- Prefer named pfSense aliases for genuinely stable approved administration sources such as office/VPN/DDNS egress. Add a FastAPI Cloud alias only if the platform later provides a stable, documented source contract or another controlled network identity.
- **TrueNAS SSH (`9922/tcp`) and firewall SSH (`22/tcp`)**: external reachability is always a failure.
- Remove broad WAN pass rules such as an Easy Rule that permits arbitrary inbound TCP. Every public listener must have an explicit port/service policy.
- **2026-09-02 acceptance evidence**: the broad WAN Easy Rule created states from observed FastAPI Cloud sources to both `7000/tcp` and `10443/tcp`. Replacing that rule remains P0. The acceptance test is source-aware: FastAPI Cloud must retain the required `7000` and `10443` paths; an independent untrusted Internet vantage point must not establish either application path; `22` and `9922` remain blocked; and no broad WAN pass may make the explicit listener/source rules ineffective.
- A successful FastAPI Cloud probe proves only the approved positive path. An HTTP `401` or `403` from an independent untrusted source still proves TCP/TLS reachability and does not satisfy an L3/L4 default-deny requirement.
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
- do not reintroduce the generic `PFSENSE_API_KEY`. Production uses separate `PFSENSE_POSTURE_API_KEY` and `PFSENSE_SECURITY_API_KEY`; rotate only the affected dedicated identity if future troubleshooting exposes or compromises it.

## P2 — Exposure observability

- Surface the expected/observed state of `10443`, `7000`, `9922`, `4000`, `22`, and other reviewed ports in `/sickz`.
- Include the exposure mechanism (`LAN-only`, `HAProxy direct`, `Cloudflare Tunnel`, `Traefik direct`) in diagnostics rather than inferring it only from the hostname.
- Surface sanitized ingress-filter telemetry in the FastAPI operations UI: pfSense/PF as a possible filtering layer in the path, plus observed service state for Snort, pfBlockerNG and CrowdSec. A running service is **not** proof that it blocked a request; block attribution requires explicit table/rule/log evidence such as `snort2c`, PF logs, pfBlocker aliases or CrowdSec decisions.
- Add bounded, cached **source-IP enrichment** for observed external addresses. The enrichment should combine RDAP/WHOIS ownership, BGP origin ASN/prefix, PTR/reverse DNS, and cloud-provider published prefix metadata when available; expose fields such as `ip`, `network`, `asn`, `asn_name`, `organization`, `country`, `rdns`, `cloud_provider`, `cloud_service`, `cloud_region`, `observed_at`, and `confidence`.
- Add an optional bounded egress-IP observation from the FastAPI Cloud runtime so a request observed by pfSense can be correlated with the application's current public source address. Treat the result as transient evidence unless the hosting platform documents a stable egress contract.
- Cache enrichment results and enforce strict timeouts/rate limits so `/healthz`, `/sickz`, and the operations UI cannot be degraded by external RDAP/ASN/echo services. Enrichment failures must remain informational and must not fail application health.
- Never expose secrets or automatically mutate pfSense aliases/firewall rules from enrichment data. Human review is required before an address/CIDR becomes an allowlist entry.
- Correlate Cloudflare Tunnel/Access evidence, TrueNAS runtime state, application-level HTTP checks, and pfSense port policy without treating any one signal as authoritative for every service.
