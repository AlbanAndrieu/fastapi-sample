# Engineering and security roadmap

This is the **canonical active roadmap** for `fastapi-sample`.

Detailed incident evidence belongs in [incidents.md](incidents.md). Operator
commands belong in focused runbooks linked from
[the documentation index](README.md). Completed implementation detail is
intentionally compacted here; Git history and tests remain the implementation
record.

## Operating constraints

- Python 3.13 and `uv` are the supported Python/tooling baseline.
- FastAPI Cloud is the canonical production runtime.
- Vercel Git deployments are disabled; Vercel must not be a merge gate.
- GitHub Actions credits are currently constrained: maximize local deterministic
  validation and use `[skip ci]` only while this explicit local-first mode is
  required.
- Optional homelab dependencies must never become application liveness
  dependencies or create probe-induced load against TrueNAS/pfSense.
- Do not weaken TLS, authentication, rate limits, timeouts or circuit breakers to
  make a health board appear green.
- Every deferred risk needs a concrete acceptance proof before it can be closed.

## P0 — production security and privacy

- [ ] Set `DEBUG=false` in FastAPI Cloud and prove unexpected exceptions no
  longer expose tracebacks.
- [ ] Audit retained FastAPI Cloud, Sentry, Logfire and centralized logs for
  credentials, reset/verification tokens and connection strings; rotate affected
  PostgreSQL or provider credentials if historical exposure is confirmed.
- [ ] Review historical commits containing private contact data and decide
  whether repository history cleanup is required.
- [ ] Replace shared operational keys with Keycloak/OIDC identities and explicit
  administration, diagnostics and MCP scopes.
- [ ] Publish a public homelab projection that excludes internal hosts, ports and
  privileged topology while preserving the operational dashboard contract.
- [ ] Add the intended Cloudflare Access/private-network restriction for
  management endpoints after the access flow is finalized.

**Acceptance:** no public traceback/secret leakage, least-privilege operational
identity, and public diagnostics reveal only intentionally published topology.

## P0 — homelab dependency convergence

The authoritative homelab observation point is the FastAPI runtime on TrueNAS.
Use workstation probes only as independent A/B evidence.

- [ ] **Talos:** grant/read `VM_READ`, show expected 3/3 VMs running, then prove
  real cluster health with `talosctl health` and `kubectl get nodes`.
- [ ] **pfSense:** recover WebGUI/PHP-FPM and require authenticated
  `GET /api/v2/system/version` to return 2xx from the TrueNAS/LAN observer.
- [ ] **Prometheus:** configure `HOMELAB_PROMETHEUS_URL` in the authoritative
  deployment and require the fixed recording-rule query to return usable data.
- [ ] **Sentry:** add a bounded synthetic event acceptance path that proves an
  event id and downstream ingestion; socket reachability alone is insufficient.
- [ ] **Pyroscope:** identify a real readiness endpoint, require 2xx, then prove
  recent profile data for `service_name=fastapi-sample`.
- [ ] Add explicit workstation-vs-TrueNAS diagnostics for pfSense and Prometheus
  without adding provider fan-out to normal health requests.
- [ ] Re-run `scripts/diagnose-local-runtime-dependencies.py` and require all
  dependency evidence contracts to be complete or explicitly deferred.
- [ ] Resume TrueNAS NFS/Kubernetes CSI acceptance only after this dependency gate
  converges.

Detailed evidence:
[local-runtime-dependency-report.md](local-runtime-dependency-report.md) and
[incidents.md](incidents.md).

## P0 — appliance protection and health latency

- [ ] Establish a measured safe probe envelope for TrueNAS and pfSense from
  Prometheus: origin rate, concurrency, p95/p99 latency, timeouts and host
  saturation.
- [ ] Attribute the remaining cold-path cost in `/api/homelab/health`; keep each
  provider timeout below the 12-second aggregate deadline rather than increasing
  the deadline.
- [ ] Define a production p95 target from fixed-cardinality phase telemetry.
- [ ] Validate that appliance degradation does not increase FastAPI error rate,
  exhaust worker threads or create request bursts.
- [ ] Keep pfSense exporter steady-state conservative: 300-second scrape interval,
  30-second Prometheus timeout, 8-second target timeout, concurrency 1 and only
  necessary collectors.
- [ ] Inventory Uptime Kuma/Gatus/AutoKuma so no automatic monitor performs
  expensive pfSense deep-status or exporter requests.
- [ ] Remove the shared-WAN Snort diagnostic blind spot before treating missing
  security telemetry as authoritative block evidence.
- [ ] Investigate the TrueNAS API client's fixed WebSocket connect timeout and
  improve bounded caller attribution without leaking URI/credential context.

Operational controls:
[external-probe-cache-operations.md](external-probe-cache-operations.md).

## P0 — canonical Nabla catalog cutover

The migration is a **direct coordinated cutover**, not a long-lived v1/v2
compatibility programme.

- [ ] Fix the producer-side `nabla-compose/catalog/services.schema.json` so
  `internalUrl` matches generated services/x-nabla metadata.
- [ ] At cutover, replace service-id/display-name joins and three-way drift checks
  with canonical full entity refs.
- [ ] Consume authoritative BIA-derived business criticality beside
  `operationalCriticality`: MTPD/DIMA, RTO, applicable RPO, recovery margin and
  assessment status.
- [ ] Remove `homelab-services.json` and
  `homelab-exposure-overrides.json` as independent authorities after all
  remaining policy exceptions have a canonical home.
- [ ] Pin a rollback commit/tag and validate stable entity refs, relation
  endpoints, exposure intent and catalog revision before cutover.

Current BIA:
[business-impact-analysis.md](business-impact-analysis.md).

## P1 — dependency automation and CI governance

- [ ] Install/validate the hosted Mend Renovate GitHub App for this repository and
  `nabla-compose`.
- [ ] After hosted-app acceptance, remove the self-hosted Renovate workflow so
  routine dependency maintenance does not consume Actions credits.
- [ ] If CVE-remediation ownership moves to Renovate, first prove Dependabot Alert
  reconciliation, then disable Dependabot Security Updates before enabling
  Renovate vulnerability PRs.
- [ ] Re-enable selective automerge only when required checks are authoritative
  and the automerged rule is tested against the current base.
- [ ] Validate master-red remediation with one intentional non-production drill:
  one failing master SHA must produce one issue and one remediation PR only.
- [ ] Review the first successful post-deployment ZAP artifacts and suppress only
  documented false positives.
- [ ] Upgrade transitive `smol-toml` to a version fixing CVE-2026-34027 via the
  pinned Node/npm toolchain; do not hand-edit the lockfile.
- [ ] Reduce the Trivy baseline and make relevant findings blocking once triaged.
- [ ] Protect `master` with reviewed PRs and final mandatory checks after normal
  CI capacity is restored.
- [ ] Decide whether merge-candidate `[skip ci]` commits should be prohibited
  only after Actions can enforce that policy again.

### Current low-churn baseline

Already implemented:

- Renovate is the routine version-update producer;
- patch/minor proposals are grouped and dev/tooling updates are scheduled less
  frequently;
- global automerge is disabled;
- `rebaseWhen=conflicted` plus manual `rebase` label is used;
- concurrent/hourly Renovate work is bounded;
- vulnerability PR ownership is not duplicated between Renovate and Dependabot;
- CI scope classification separates `none`, `quality` and `full`;
- quality-only config changes avoid a full dependency bootstrap/application build;
- external GitHub Actions are pinned to immutable SHAs.

## P1 — release and deployment

- [ ] Trigger FastAPI Cloud deployment from the existing
  `semantic-release-published` repository dispatch.
- [ ] Validate/deploy the immutable release tag rather than a moving branch.
- [ ] Consolidate push/release production rollout after the repaired release
  sequence is observed.
- [ ] Publish container images with semantic-version and commit-SHA tags, signed
  provenance and generated SBOM artifacts.
- [ ] Store generated SBOM reports as CI artifacts rather than tracked large files.
- [ ] Disconnect the Git provider from the Vercel project with an authorized
  Vercel identity.
- [ ] Acceptance for Vercel disablement: a later PR push produces no Vercel
  deployment, status check or PR comment.

## P1 — runtime architecture

- [ ] Introduce an application factory so tests can create a minimal app without
  PostgreSQL, Redis, observability, MCP or RAG side effects.
- [ ] Move remaining global DB/Redis resources behind application lifecycle/state
  or injected dependencies.
- [ ] Consolidate SQLAlchemy/`databases`/psycopg pools behind one lifecycle and
  move schema creation to explicit Alembic deployment migrations.
- [ ] Split dependency groups into clear runtime/observability/homelab/AI/dev
  boundaries and then reduce production image size.
- [ ] Replace the Git-tagged TrueNAS client dependency with an immutable commit or
  maintained release.
- [ ] Create lifespan-owned shared `httpx.AsyncClient` pools with consistent
  connect/read/write/pool budgets and stricter provider-specific overrides.
- [ ] Keep unit tests hermetic and network-disabled; perform LAN acceptance only
  through explicit integration/diagnostic commands.

### Completed runtime baseline

Already implemented and retained by tests:

- AsyncExitStack lifecycle cleanup and partial-startup rollback;
- explicit shutdown for Redis/PostgreSQL/MCP resources;
- bounded provider deadlines, circuit breakers, stale-cache behavior and
  concurrency;
- no mandatory Cloudflare/Sentry/Prometheus dependency for core liveness;
- Datadog imports/profiler are opt-in and lifecycle-owned;
- Sentry PII defaults remain disabled;
- key health-board modules were split below maintainability thresholds;
- Notes write paths are asynchronous and return persisted identifiers.

## P2 — application/domain backlog

Keep these lower-priority items concise until they become active work:

- [ ] Finish Notes model normalization: boolean `completed`, timezone-aware
  timestamps, read/delete response models and complete CRUD/integration coverage.
- [ ] Replace mutable global RAG vector state with a concurrency-safe
  `VectorStore` abstraction and persistent production implementation.
- [ ] Add SearXNG in `nabla-compose` and then evaluate a bounded optional adapter;
  do not make it mandatory for search.
- [ ] Continue MCP SDK review and evaluate any pfSense MCP service only as a
  private, least-privilege component.
- [ ] Evaluate FastAPI Radar only as an opt-in local development tool because it
  can capture request/response data.
- [ ] Complete semantic review of remaining PR #63 divergent/absent files; port
  behavior, not stale files.
- [ ] Merge duplicate Compose development files/profiles and archive obsolete
  Dockerfiles only after proving they are unused.
- [ ] Deduplicate Cursor/Codex/OpenCode/Copilot policy; keep `AGENTS.md` as the
  shared agent contract.

## Documentation and incident policy

- [x] Use [docs/README.md](README.md) as the documentation navigation page.
- [x] Group reusable incident evidence in [incidents.md](incidents.md).
- [x] Keep detailed recovery commands in focused runbooks instead of duplicating
  them in this roadmap.
- [x] Compact completed roadmap history into capability baselines.
- [ ] When a new incident occurs, add only reusable recognition/recovery evidence
  to the incident register; do not paste full investigation transcripts here.

## Completion gate

Before declaring a roadmap item complete:

1. run the smallest deterministic local test that proves the behavior;
2. run the repository quality gate appropriate to the CI scope;
3. record any missing external/runtime acceptance proof here;
4. update [incidents.md](incidents.md) only if a new reusable diagnostic rule was
   learned;
5. keep the PR unmerged when a required validation remains unavailable.

### Local-first validation

```bash
bash scripts/agent-quality-gate.sh --fix
bash scripts/agent-quality-gate.sh
```

For release candidates, use the publication gate after the tree is clean.
