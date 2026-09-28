# Documentation index

This directory is organized by **operator task**, not by implementation history.
The goal is to make the shortest path to a diagnosis obvious while keeping
detailed evidence available when it matters.

## Start here

- [Engineering roadmap](engineering-roadmap.md) — active work, priorities,
  acceptance criteria and compact completed baseline.
- [Incident register](incidents.md) — known incidents, decisive evidence,
  recovery path and links to detailed runbooks.
- [Application entry points and dashboards](entrypoints-and-dashboards.md) —
  current API, MCP and local dashboard entry points.
- [Business Impact Analysis](business-impact-analysis.md) — RTO, MTPD/DIMA,
  RPO and recovery assumptions.

## Operations and diagnostics

Use these documents when the service or one of its dependencies is unhealthy.

| Area | Primary document | Purpose |
| --- | --- | --- |
| Runtime dependencies | [Local runtime dependency convergence](local-runtime-dependency-report.md) | TrueNAS/pfSense/Prometheus/Cloudflare/Sentry evidence matrix and A/B checks |
| Health environment | [Health monitoring environment](health-monitoring-environment.md) | Runtime settings and endpoint responsibility |
| Health semantics | [Platform service diagnostics model](platform-service-diagnostics-model.md) | How evidence becomes service state in the UI |
| Probe protection | [External probe cache operations](external-probe-cache-operations.md) | Cache, rate, circuit-breaker and Redis-degraded behavior |
| pfSense recovery | [pfSense webConfigurator recovery](pfsense-webconfigurator-recovery.md) | Preserve evidence and recover PHP-FPM/WebGUI 502 safely |
| pfSense security | [pfSense security observability](pfsense-security-observability.md) | Read-only security and posture evidence |
| Public ingress | [TrueNAS public ingress](truenas-public-ingress.md) | TCP/TLS/firewall attribution and Snort/pfBlocker/CrowdSec isolation |
| Cloudflare/Sentry | [Cloudflare and Sentry runtime diagnostics](cloudflare-sentry-runtime-diagnostics.md) | Provider evidence and failure semantics |
| Cloudflare path | [Cloudflare network contract](fastapi-sample-cloudflare-network-contract.md) | Expected network and Tunnel path |

## Architecture and security

- [API/UI architecture](api-ui-architecture.md)
- [Homelab security and resilience plan](homelab-security-roadmap.md)
- [Kubernetes zero-trust hardening](kubernetes-zero-trust-hardening.md)
- [MCP integrations](mcp-integrations.md)
- [TrueNAS public ingress diagnostics](truenas-public-ingress.md)

## Historical and evaluation material

These documents remain useful as evidence but are not active roadmaps:

- [Cashews evaluation](cashews-evaluation.md)
- [Cloudflare Tunnel audit](cloudflare-tunnel-audit.md)
- [Release 1.4.0 reset](release-1.4.0-reset.md)
- [Release 1.4.1](release-1.4.1.md)
- [Release 1.5.8](release-1.5.8.md)
- [Snort WAN validation](snort-wan-validation.md)

## Documentation rules

1. **Roadmaps contain future work, not incident transcripts.**
2. **Incidents live in the incident register** and link to detailed runbooks.
3. **Runbooks preserve diagnostic evidence**: symptom, vantage point, command or
   probe, decisive result, recovery and recurrence check.
4. Completed roadmap work is compacted into a short baseline; Git history and
   focused runbooks retain implementation detail.
5. Do not duplicate the same operational fact in multiple files. Prefer one
   canonical document plus links.
