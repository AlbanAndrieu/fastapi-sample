# Engineering and security roadmap

This is the **single prioritized roadmap** for `fastapi-sample`.

Operational evidence and recovery commands belong in focused runbooks. Dated
failures belong in [incidents.md](incidents.md). Completed implementation is
represented here only as compact guardrails; tests and Git history remain the
detailed implementation record.

## Operating constraints

- Python 3.13 + `uv` are the supported Python/tooling baseline.
- FastAPI Cloud is the canonical production runtime.
- Vercel Git deployment is disabled and must not be a merge gate.
- GitHub Actions capacity is constrained: prefer deterministic local validation.
- Optional homelab integrations must not become application liveness dependencies.
- Never weaken TLS, authentication, timeouts, cache/circuit breakers or rate
  limits merely to make health status appear green.
- Close a roadmap item only with an explicit acceptance proof.

## P0 — production security and privacy

- [ ] Set `DEBUG=false` in FastAPI Cloud and prove unexpected exceptions no
  longer expose tracebacks.
- [ ] Audit retained FastAPI Cloud/Sentry/Logfire/centralized logs for credentials,
  reset/verification tokens and connection strings; rotate affected credentials
  if historical exposure is confirmed.
- [ ] Review historical commits containing private contact data and decide whether
  repository history cleanup is required.
- [ ] Replace shared operational keys with Keycloak/OIDC identities and explicit
  administration, diagnostics and MCP scopes.
- [ ] Finish the public homelab projection beyond topology. The browser topology
  now uses a sanitized relation graph without internal URLs, ports, runtime
  networks, source paths or configuration evidence; full service, declared,
  runtime and reconciliation endpoints are diagnostics-key protected. Apply the
  same least-data boundary to any future public diagnostics.
- [ ] Apply the intended Cloudflare Access/private-network restriction to
  management endpoints once the access flow is finalized.

**Acceptance:** no public traceback/secret leakage, least-privilege operational
identity, and public diagnostics expose only intentionally published topology.

## P0 — homelab dependency convergence

The authoritative observer is the FastAPI runtime on TrueNAS. Workstation probes
are independent A/B evidence only.

- [x] **Talos / TrueNAS VM evidence:** `VM_READ` granted and expected 3/3
  Talos VMs observed `RUNNING` through `vm.query`.
- [ ] **Talos cluster health:** prove the guest cluster with `talosctl health`
  and `kubectl get nodes`; TrueNAS VM state alone is insufficient.
- [ ] **pfSense:** recover WebGUI/PHP-FPM and require authenticated
  `GET /api/v2/system/version` 2xx from the TrueNAS/LAN observer.
- [ ] **Prometheus:** configure `HOMELAB_PROMETHEUS_URL` in the authoritative
  deployment and require usable query/recording-rule evidence.
- [ ] **Sentry:** prove a bounded synthetic event ID and downstream ingestion;
  socket reachability is insufficient.
- [ ] **Pyroscope:** identify a real readiness endpoint and prove recent profile
  data for `service_name=fastapi-sample`.
- [ ] Add workstation-vs-TrueNAS diagnostics for pfSense and Prometheus without
  adding provider fan-out to normal health requests.
- [ ] Re-run `scripts/diagnose-local-runtime-dependencies.py` and require every
  dependency contract to be complete or explicitly deferred.
- [ ] Resume TrueNAS NFS/Kubernetes CSI acceptance after this gate converges.

Runbook:
[local-runtime-dependency-report.md](local-runtime-dependency-report.md).

## P0 — appliance protection and health latency

- [ ] Measure a safe TrueNAS/pfSense probe envelope: origin rate, concurrency,
  p95/p99 latency, timeouts and host saturation.
- [ ] Attribute remaining cold-path cost in `/api/homelab/health`; keep provider
  budgets below the aggregate deadline rather than extending that deadline.
  - [x] Run TrueNAS HTTP/API/LAN/transport evidence concurrently; within the
    transport probe, overlap DNS with hostname TCP/TLS and start direct WAN+SNI
    fallback as soon as DNS proves a path mismatch. Keep the 3 s diagnostic
    budget and preserve measured HTTP evidence when auxiliary diagnostics time out.
  - [x] Compare hostname TLS with direct WAN-IP+SNI on port 7000 so DNS/edge
    drift is distinguishable from pfSense/HAProxy failure.
- [ ] Define a fixed-cardinality production p95 latency target.
- [ ] Prove appliance degradation cannot exhaust FastAPI workers or create probe
  bursts.
  - [x] Fail fast on pfSense HTTP 401 so one rejected posture key does not fan
    out into multiple authentication failures.
  - [x] When authenticated pfSense `system.version` preflight takes >=2.5 s,
    preserve liveness/auth evidence, expose a slow-control-plane warning and
    skip deeper posture fan-out for that refresh.
  - [ ] Validate the 2.5 s protection threshold against measured p95/p99
    latency and appliance CPU/RAM/PHP-FPM saturation evidence.
    - [x] Export fixed-cardinality Prometheus histogram evidence for the
      existing `system.version` preflight and counters for protective fan-out
      skips; this adds no provider request.
    - [x] Preserve the latest successful preflight latency in the sanitized
      posture as `control_plane_elapsed_ms`, with
      `control_plane_state=ok|slow` and explicit `deep_probe_skipped`.
    - [ ] Collect a sustained TrueNAS-runtime baseline and correlate p95/p99,
      skip rate, provider in-flight work and pfSense CPU/RAM/PHP-FPM/FastCGI
      evidence before changing the 2.5 s threshold.
  - [ ] Correlate bounded pfSense nginx/pfREST evidence with the passive
    `Nabla-Probe-Origin`, `Nabla-Probe-Name`, `Nabla-Probe-Request-ID`
    and W3C trace context fields, without logging API keys or treating probe
    metadata as an authorization signal.
- [x] Inventory Uptime Kuma/Gatus/AutoKuma: current generated monitors use only
  TCP `172.17.0.1:10443` for pfSense and TCP `:9945` for the pfSense
  exporter; AutoKuma explicitly forbids exporter `/metrics` health checks
  because they fan out into pfREST.
- [ ] Reconcile the latent `nabla-compose/apps/crowdsec/compose.yml`
  `pfsense.monitoring` metadata, which still declares HTTP
  `/api/v2/system/version`, with the lightweight TCP monitoring policy so a
  future catalog-consumer regeneration cannot reintroduce periodic pfREST
  load.
- [x] Remove the shared-WAN Snort attribution blind spot from the authoritative
  observer path: TrueNAS/homelab uses the LAN/split-DNS `out_of_band` control
  path for pfSense API evidence, while FastAPI Cloud authenticated pfSense
  probes remain disabled and WAN reachability is observed separately.
- [ ] After an independent pfSense observer path is accepted, expand the
  sanitized posture with interfaces/gateways, firewall/NAT and DNS policy;
  query VPN, logs and private inventory only for explicit operational needs.
- [x] Preserve expected exposure reachability in low-level `/sickz` rows so
  policy-enrichment timeouts cannot turn a required positive probe green.
- [ ] Improve TrueNAS WebSocket timeout attribution without leaking URI or
  credential context.

Runbook:
[external-probe-cache-operations.md](external-probe-cache-operations.md).

## P0 — canonical Nabla catalog cutover

The migration remains a **direct coordinated cutover**, not a v1/v2 compatibility
programme.

- [ ] Fix `nabla-compose/catalog/services.schema.json` so `internalUrl` matches
  generated services/x-nabla metadata.
- [ ] Replace service-id/display-name joins and three-way drift checks with
  canonical full entity refs.
- [ ] Consume authoritative BIA-derived business criticality beside
  `operationalCriticality`.
- [ ] Remove `homelab-services.json` and `homelab-exposure-overrides.json` as
  independent authorities after remaining exceptions have a canonical home.
- [ ] Pin rollback evidence and validate stable entity refs, relation endpoints,
  exposure intent and catalog revision before cutover.
  - [x] Keep a validated packaged topology snapshot for cold-start resilience;
    `nabla-compose` remains authoritative and stale runtime data remains preferred.
  - [x] Align the topology consumer with canonical Talos `truenas-vm`,
    `runtime.instances` and provider-monitoring metadata.
  - [ ] Add an explicit catalog revision/provenance field so deployed runtime,
    remote origin and packaged fallback can be compared without log inference.

Reference:
[business-impact-analysis.md](business-impact-analysis.md).

## P1 — dependency automation and CI governance

- [ ] Validate the hosted Mend Renovate GitHub App for this repository and
  `nabla-compose`.
- [ ] After acceptance, remove the self-hosted Renovate workflow.
- [ ] If CVE ownership moves to Renovate, prove Dependabot Alert reconciliation
  before disabling Dependabot Security Updates and enabling Renovate fixes.
- [ ] Re-enable selective automerge only when required checks are authoritative
  and current-base validation is guaranteed.
- [ ] Validate master-red remediation with one controlled non-production drill.
- [ ] Review the first successful post-deployment ZAP artifacts and suppress only
  documented false positives.
- [ ] Upgrade transitive `smol-toml` to a version fixing CVE-2026-34027 through
  the pinned Node/npm toolchain.
- [ ] Reduce the Trivy baseline and make relevant triaged findings blocking.
- [ ] Protect `master` with reviewed PRs and final required checks once normal CI
  capacity is restored.
- [ ] Decide whether merge-candidate `[skip ci]` must then be prohibited.

## P1 — release and deployment

- [ ] Trigger FastAPI Cloud deployment from the existing
  `semantic-release-published` repository dispatch.
- [ ] Deploy immutable release tags instead of a moving branch.
- [ ] Consolidate push/release rollout after the repaired release sequence is
  observed.
- [ ] Publish images with semantic-version and commit-SHA tags, signed provenance
  and generated SBOM artifacts.
- [ ] Keep generated SBOMs as artifacts rather than tracked large files.
- [ ] Disconnect the Git provider from the Vercel project with an authorized
  identity.
- [ ] Prove a later PR push creates no Vercel deployment, status or comment.

## P1 — runtime architecture

- [ ] Introduce an application factory so tests can create a minimal app without
  PostgreSQL, Redis, observability, MCP or RAG side effects.
- [ ] Move remaining global DB/Redis resources behind lifecycle/state or injected
  dependencies.
- [ ] Consolidate SQLAlchemy/`databases`/psycopg lifecycle and move schema
  creation to explicit Alembic deployment migrations.
- [ ] Split dependency groups into runtime/observability/homelab/AI/dev boundaries
  and reduce the production image.
- [ ] Replace the Git-tagged TrueNAS client dependency with an immutable commit or
  maintained release.
- [ ] Create lifespan-owned shared `httpx.AsyncClient` pools with explicit
  connect/read/write/pool budgets.
- [ ] Keep unit tests hermetic; perform LAN acceptance only through explicit
  integration/diagnostic commands.

## P2 — application/domain backlog

- [ ] Finish Notes normalization: boolean `completed`, timezone-aware timestamps,
  read/delete response models and complete CRUD/integration coverage.
- [ ] Replace mutable global RAG vector state with a concurrency-safe
  `VectorStore` abstraction and persistent implementation.
- [ ] Add SearXNG in `nabla-compose`, then evaluate a bounded optional adapter.
- [ ] Continue MCP SDK review; keep any pfSense MCP service private and
  least-privilege.
- [ ] Consolidate duplicate Compose/Docker development paths: current repository
  references show `Dockerfile-pipenv` and `Dockerfile-poetry` are orphaned, while
  `docker-compose.yml` still backs legacy/dev PostgreSQL/Redis tooling. Prove the
  canonical `Dockerfile` + `docker-compose.yaml` build/smoke locally, reconcile
  remaining Makefile/mise/helm references, then remove only the unused paths.

## Implemented guardrails — compact baseline

Do not expand these back into historical checklists unless a regression occurs:

- bounded health probes, single-flight/SWR cache, circuit breakers and aggregate
  deadlines;
- separation of transport, application, auth and workload evidence;
- optional provider failures do not automatically become global DOWN;
- Cloudflare/Sentry/Prometheus are not core liveness dependencies;
- lifecycle cleanup/rollback for application-owned resources;
- Datadog/Sentry observability is opt-in with PII disabled by default;
- service/topology/BIA projections are typed at the current contract boundary;
- Renovate is low-churn, automerge is disabled and duplicate CVE PR ownership is
  avoided;
- CI scopes are `none`, `quality` and fail-closed `full`;
- changed Markdown links are validated locally without network access;
- large-deletion acknowledgements are bound to the exact comparison-base SHA;
- external GitHub Actions are pinned to immutable SHAs;
- Vercel Git deployments are repository-disabled;
- `AGENTS.md` is the single global agent policy; Claude, Copilot, Cursor and
  OpenCode use thin adapters and task-scoped rules instead of duplicated policy;
- FastAPI Radar was evaluated and remains intentionally absent from runtime;
  any future adoption must be local-only, disabled by default, authenticated,
  redacted and covered by disabled-mode tests;
- retired legacy branches are not replayed wholesale: current Pylint, TrueNAS,
  catalog and dashboard implementations are authoritative; mutable-global RAG
  prototypes remain rejected in favor of the open `VectorStore` item;
- agent policy/skill changes use the isolated `quality` scope, and local/CI
  quality gates execute the same contract-test set;
- health-board modules already split for maintainability remain covered by tests.

## Documentation policy

1. This file contains **open work only**, plus the compact baseline above.
2. Dated incidents belong in [incidents.md](incidents.md).
3. Commands and recovery procedures belong in focused runbooks.
4. Avoid copying the same observed state into roadmap + incident + runbook.
5. A resolved incident contributes only a reusable rule/guardrail here.

## Completion gate

Before closing an item:

1. run the smallest deterministic local proof;
2. run the quality gate appropriate to its CI scope;
3. record any missing external/runtime acceptance proof;
4. update the incident register only if a reusable diagnostic rule was learned.

```bash
bash scripts/agent-quality-gate.sh --fix
bash scripts/agent-quality-gate.sh
```
