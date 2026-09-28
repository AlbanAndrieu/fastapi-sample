# Documentation

Documentation is organized by **operator task**, not implementation history.

## Canonical documents

| Need | Document |
| --- | --- |
| What remains to do? | [Engineering roadmap](engineering-roadmap.md) |
| Has this happened before? | [Incident register](incidents.md) |
| How is health evidence interpreted? | [Platform diagnostics model](platform-service-diagnostics-model.md) |
| How do I validate local runtime dependencies? | [Local runtime diagnostic](local-runtime-dependency-report.md) |
| What are the stable homelab security rules? | [Homelab security guardrails](homelab-security-roadmap.md) |
| What are the continuity targets? | [Business Impact Analysis](business-impact-analysis.md) |
| Where are APIs/dashboards? | [Entry points and dashboards](entrypoints-and-dashboards.md) |

## Runbooks

- [pfSense WebGUI/API 502 recovery](pfsense-webconfigurator-recovery.md)
- [pfSense security observability](pfsense-security-observability.md)
- [External probe cache operations](external-probe-cache-operations.md)
- [TrueNAS public ingress](truenas-public-ingress.md)
- [Cloudflare/Sentry runtime diagnostics](cloudflare-sentry-runtime-diagnostics.md)
- [Cloudflare network contract](fastapi-sample-cloudflare-network-contract.md)
- [Health monitoring environment](health-monitoring-environment.md)
- [Kubernetes zero-trust hardening](kubernetes-zero-trust-hardening.md)

## Architecture/reference

- [API/UI architecture](api-ui-architecture.md)
- [MCP integrations](mcp-integrations.md)
- [Cloudflare Tunnel audit](cloudflare-tunnel-audit.md)
- [Snort WAN validation](snort-wan-validation.md)
- [Cashews evaluation](cashews-evaluation.md)

Release notes under `docs/release-*.md` are historical records, not active
roadmaps.

## Documentation rules

1. **One roadmap:** `engineering-roadmap.md`.
2. **One incident register:** dated symptom/cause/recognition evidence goes in
   `incidents.md`.
3. **Runbooks are timeless:** keep commands, safety constraints and acceptance
   criteria; remove dated status snapshots once captured in the incident register.
4. **Completed work is compacted:** keep only durable guardrails/capabilities in
   the roadmap; tests and Git history hold implementation detail.
5. **No duplicated truth:** link to the canonical document rather than copying a
   state matrix or command sequence.
6. **Diagnostic essentials are never removed:** observer vantage point, first
   failing layer, decisive command/probe, expected result, recovery safety and
   acceptance criteria must remain recoverable.
