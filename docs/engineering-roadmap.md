# Engineering and security roadmap

## P1 — Catalogue de criticité et sondes par unité de déploiement (2026-10-17)

Reference: [nabla-compose PR #257](https://github.com/AlbanAndrieu/nabla-compose/pull/257), `docs/watchtower-service-units.md`. **Roadmap only**; do not imply the current probe runtime has already changed.

- [ ] Reconcile canonical `x-nabla` and its catalog-v2 revision with FastAPI package fallback, origin and live TrueNAS apps. Preserve the existing direct v2 cutover plan (no permanent v1/v2 shim).
- [ ] Distinguish `operationalCriticality` from BIA-derived `businessCriticality`; do not infer business criticality from display role or use a missing value as Low. Reuse catalog unit-level `stateful`, `upgradePolicy` and dependency metadata for *display/observation*, not an administrative Docker control plane.
- [ ] Add normalized `deploymentUnitId`, logical endpoint/member relations, `probePolicy` and ordered dependencies in the canonical catalog. The keys `garage` (S3 :3900), `garage-admin` (Admin :3903) and `garage-webui` (UI :3909) remain distinct but share `truenas:garage` for scheduling, caching and upgrade-policy grouping.
- [ ] Replace three parallel Garage fan-outs with a bounded, serialized, cache-aware **per-unit** probe sequence: primary read-only S3 probe, conditional Admin probe and WebUI probe, with shared cooldown, singleflight, capped concurrency and per-endpoint evidence/staleness. Use the dependency DAG for ordering; separate internal and outside-in observers. Never repeatedly hammer Admin API or Cloudflare Access.
- [ ] Preserve #342's **12-target sampling budget with 10 prioritized + 2 rotating slots**, rotating across units and independently tracking component coverage; prevent starvation even if selected units have multiple endpoints. A group counts as one scheduling selection, **not** a promise of unlimited probes.
- [ ] Preserve independent health vs exposure intent: `external=false` requires LAN validation and outside-in exposure audit; Cloudflare 302/403 does not prove origin health or exposure; stale/missing LAN evidence must not turn DOWN or GREEN without proof. Timeouts become warning/unknown, not speculative runtime DOWN.
- [ ] Add regression tests for Garage unit deduplication, priority order, no-starvation rotation, 1–3 target budgets, TTL and stale evidence, access-protected probes, and conservative degradation. Measure probes/minute, concurrency, latency and TrueNAS/pfSense CPU before/after. Avoid changing the production cloud's no-LAN-probe posture.
- [ ] Publish unit-level summary + per-component evidence and provenance on health-board only after local-first quality gate, synchronized catalog revisions and accepted rollback plan.

## P1 — Garage : couverture des sondes LAN et reconciliation DNS (2026-10-13)

- [x] Conserver `garage` (S3 API :3900), `garage-admin` (Admin API :3903) et `garage-webui` (Web UI :3909) dans l'échantillonnage prioritaire des sondes internes, même lorsque le catalogue dépasse le budget de 12 cibles par cycle. Ne pas activer les sondes LAN sur la production cloud.
- [x] Corriger la saturation des 12 places de priorité : réserver deux places à la rotation des services non prioritaires et aligner l'estimation de fréquence des sondes, y compris les cas de budget nul. Vérification par tests de non-famine ajoutés ; exécution locale en attente.
- [x] Vérifier dans le catalogue source que les deux API sont `external=false`, avec WebUI `external=true` temporairement ; maintenir des noms explicites sans réutiliser l'identifiant technique de l'API pour l'UI.
- [x] La couverture des preuves de sondes exclut maintenant les lignes `probe_stale=true` et les échéances sans observation : elles restent consultables mais ne sont plus comptées comme des preuves valides. Test de non-régression ajouté ; exécution locale encore requise.
- [x] Séparer la politique `internal` de l'état fonctionnel : une sonde LAN valide peut confirmer la santé d'une API privée, un ancien tunnel Cloudflare ne dégrade pas directement sa santé mais génère `unexpected_tunnel_route=true` (à auditer), et une preuve LAN périmée ne compte plus comme santé actuelle. Tests ajoutés, exécution encore requise.
- [ ] Après déploiement, vérifier `/api/health-board` → `homelab.services` et `homelab.internal_services` depuis FastAPI sur TrueNAS et workstation. Le cloud observer ne peut pas prouver la santé LAN ; absence de sonde ≠ DOWN.
- [x] Documenter le runbook `docs/runbooks/garage-public-ingress-audit.md`, y compris les commandes pour comparer catalogue, DNS public, Cloudflare Tunnel, HAProxy/NAT, Traefik et réponses outside-in sans divulguer les paramètres signés de Cloudflare Access.
- [ ] Auditer les origines actives Cloudflare Tunnel : `garage.albandrieu.com` a renvoyé du XML S3 ; le 2026-10-15, `garage-admin.albandrieu.com` renvoie `HTTP/2 302` vers le login Cloudflare Access. Cela confirme une route publique à l'edge, mais ne prouve pas l'accès anonyme à l'origine ni son port. Comparer les ports :3900/:3903/:3909, routes Access et contenu de réponse ; retirer l'ingress public Admin API après confirmation de sa source de configuration.
- [ ] Intégrer l'audit DNS public + HAProxy/NAT pfSense + Traefik + Cloudflare dans un rapport de drift `declared/observed/unknown`, avec preuves outside-in. La politique privée n'est pas une preuve d'inaccessibilité WAN.
- [ ] Évaluer accès privé distant via Tailscale/WireGuard pour retirer à terme la WebUI de l'Internet public ; en attendant, conserver uniquement l'UI publiable derrière contrôle d'accès.
- [x] Exécuter localement les tests ciblés et la quality gate complète sur le checkout réel (2026-10-16, `agent-publish.sh` sur le HEAD de #342) ; ne pas consommer GitHub Actions pour une validation non nécessaire et ne pas merger automatiquement.
- [x] Budgets minuscules (`limit` 1 à 3) saturés par les priorités : l'estimation de fréquence renvoie `None` au lieu d'une division par zéro. Couvert par un test paramétré 1/2/3.
- [x] Remplacer le double ensemble en dur (`_PRIORITY_SERVICE_IDS` + `garage_ids`) par un ordre unique `_PRIORITY_SERVICE_ORDER` : quand les 12 priorités dépassent les 10 places fixes, les moins bien classées (`n8n`, `pyroscope`) passent en rotation de façon déterministe, indépendamment de l'ordre du catalogue, et sont exposées dans `homelab.{public,internal}.rotated_priority_ids`.
- [ ] **Cross-repo `nabla-compose`** — déclarer la priorité de sonde dans le catalogue au lieu du code : ajouter un champ optionnel `probePriority` (entier, rang croissant, absent = rotation) dans `catalog/homelab-exposure-overrides.json`, avec validation de schéma côté `nabla-compose`. Regrouper par composant via `sourcePath` (ex. `apps/garage/compose.yml` → `garage`, `garage-admin`, `garage-webui`) plutôt que par liste d'identifiants. Ne pas dériver la priorité de `criticality` : 30 nœuds `critical`/`high` dépassent le budget de 12.
- [ ] **Catalogue `fastapi-sample`** — après publication du champ dans `nabla-compose` : ajouter `probe_priority: int | None` à `HomelabService` (alias `probePriority`), le propager par `_apply_exposure_overrides`, faire lire le rang à `homelab_probe_policy._probe_partitions`, puis supprimer `_PRIORITY_SERVICE_ORDER` en gardant un repli bootstrap identique tant que le catalogue distant n'expose pas le champ. Preuve d'acceptation : test de contrat sur le catalogue bootstrap (rangs Garage 0–2 attendus), test de sélection lisant le rang depuis le catalogue, et `rotated_priority_ids` inchangé pour le catalogue actuel.


- [ ] **P0 Cloudflare Access probe evidence** (partial: unconfirmed Access and missing authenticated HTTP status now remain warnings; focused regression tests added, execution pending) — exporter et tester `cloudflare_access_secondary_probe_eligible`, `cloudflare_access_secondary_probe_attempted` et `public_probe_verification` afin de différencier HTTP 403 anonyme protégé, service token refusé et origine réellement sondée. Vérifier les cas IT Tools et Karakeep contre réponses anonymes et résultats LAN, sans convertir un refus Access en application saine.


This is the **single prioritized roadmap** for `fastapi-sample`.

Operational evidence and recovery commands belong in focused runbooks. Dated
failures belong in [incidents.md](incidents.md). Completed implementation is
represented here only as compact guardrails; tests and Git history remain the
detailed implementation record.

**P0 Cloudflare Access implementation note (2026-10-10):** Rejecting a service token is now a distinct diagnostic from origin failure; a 2xx/3xx authenticated response with no `origin_reached` evidence remains `warn`. Regression tests were added. Live TrueNAS/Cloudflare acceptance and exact-HEAD local quality gate remain outstanding.

### P0 — Audit de sécurité Cloudflare (à réaliser)

- [ ] Examiner et valider la provenance, les permissions et les prérequis du dépôt officiel [cloudflare/security-audit-skill](https://github.com/cloudflare/security-audit-skill) avant installation (version/commit épinglé, principe du moindre privilège).
- [ ] Installer le skill dans un environnement isolé et exécuter **un audit en lecture seule** des zones Cloudflare pertinentes pour fastapi-sample et les services publics du homelab : Cloudflare Access, politiques, Service Tokens, WAF, tunnels, DNS et risques de contournement d'authentification.
- [ ] Enregistrer les résultats dans un rapport de sécurité **assaini** (sans jetons, identifiants sensibles ou secrets) ; distinguer constats vérifiés, points non accessibles et recommandations.
- [ ] Réconcilier les observations avec les sondes outside-in de FastAPI Cloud et les diagnostics TrueNAS, sans assimiler un service accessible à un service sécurisé ; produire des actions correctives testables et priorisées.
- [ ] N'appliquer **aucun changement de politique Cloudflare** automatiquement : revue et autorisation explicites avant toute modification ; valider ensuite l'absence de régression Access et le fonctionnement des Service Tokens.

## Consolidated execution plan — 2026-10-10

This section is a **navigation and acceptance index**, not a second backlog.
Detailed requirements remain in the P0/P1/P2 sections below. Reassess the
priority against new incidents before each PR; never mark an item completed on
the strength of an earlier PR's CI result.

| Order | Workstream | Next bounded deliverable | Acceptance evidence |
| --- | --- | --- | --- |
| P0 | Production security/privacy | Verify Cloud DEBUG and sanitized diagnostics after an authorized deployment | No public traceback or sensitive endpoint detail; no production fault injection |
| P0 | pfSense/TrueNAS resilience | Correlate passive p95/p99 and appliance resource saturation before adjusting probe budgets | TrueNAS-origin evidence with bounded request rate, warnings and no extra fan-out |
| P0 | Canonical catalog cutover | Confirm v2 schema/entity refs, provenance and rollback snapshot with nabla-compose | Validated revision parity and deterministic reconciliation; direct cutover, no compatibility layer |
| P1 | Offline local-first & CI | Validate the exact GitHub HEAD against a trustworthy local snapshot without depending on live DNS/git clone | SHA provenance, offline tests, formatter/security checks and explicit missing-proof report |
| P1 | Agent efficiency | Summarize failing checks by job/step, preserve complete logs locally, avoid repeated full-context reads | Bounded terminal output, evidence paths, no suppressed failure and no unnecessary Actions dispatch |
| P1 | Portable CI | Pilot Dagger with the existing scripts as the initial source of truth | Same SHA and checks yield equivalent exit codes locally and in CI; version pinned |
| P1 | Dual-vantage monitoring | Run SOS runner/model subset for public checks, compare with existing HTTPX/dnspython/AnyIO evidence | DNS/TLS/HTTP/Access semantics preserved and measured net LOC reduction |
| P1 | Runtime architecture | Extract app factory and lifecycle-owned HTTPX/DB/Redis resources incrementally | Hermetic tests with no network/DB side effects at import |
| P2 | Domain backlog | Tackle notes contract, VectorStore/RAG, SearXNG, MCP and container cleanup separately | Focused contracts, migrations or integration tests as appropriate |

### Local-first DNS-failure policy

1. Reuse a verified local checkout and existing `uv` cache first. Never assume
    that an inaccessible hostname proves the repository, test or dependency is
    broken. Do not patch `/etc/hosts`, disable TLS validation or use unverified
    IP-address substitution to bypass DNS.
2. When `git clone` cannot resolve GitHub, fetch an **exact immutable commit
    archive** only through an already available authenticated/trusted download
    channel. Record the commit SHA, source URL and archive digest; check archive
    paths before extraction. A branch-named moving archive is insufficient.
3. Run `uv sync --frozen --offline` only when the locked distributions are in
    cache; otherwise report `BLOCKED_DEPENDENCIES`, do not replace/pin packages
    speculatively. If dependencies already exist, prefer `uv run --no-sync`.
4. Run focused tests, deterministic fix convergence, strict quality gate and
    publication proof against the **same immutable HEAD**. Preserve stdout/stderr
    in local logs; display only a concise failing-step summary and log path.
5. Distinguish `PASS`, `FAIL` and `NOT_RUN/BLOCKED` for each check. In no-credit
    mode use `[skip ci]`, keep the PR Draft, never rerun Actions and never claim
    CI green when it did not execute.
6. Implement the snapshot materializer as a narrow, separately tested utility
    before integrating it with Just/Dagger. Its negative tests must reject path
    traversal, symlink escapes, wrong SHA/provenance and incomplete archives.

### Agent token budget policy

- Read PR state and failing jobs once; expand to failing steps, then specific log
  excerpts. Reuse SHA-bound evidence until HEAD changes.
- Default pytest failure summary: 20 lines, maximum 40; complete failure log
  remains on disk. Do not send full test suites, lockfiles or trace dumps into
  the agent context unless needed to resolve the failure.
- Keep `AGENTS.md` global and project skills task-scoped; no duplicated agent
  policy in the roadmap, CI YAML or client adapters.
- Quantify cost using output lines/tokens and wall time **before/after** on the
  same failing fixture; reductions must not weaken checks or discard evidence.

## P0 integration checkpoint — Gatus / Prometheus / OpenRAG (2026-10-10)

- [x] Inspect the existing internal Gatus-via-Prometheus implementation:
  `nabla/api/platform_metrics.py` queries bounded recording rules;
  `nabla/api/synthetic_probe_comparison.py` only compares matching internal
  service IDs. HTTP application checks do not count as TCP transport mismatches.
- [x] Harden the internal comparison/delegation contract against non-finite,
  out-of-range and boolean success samples, with dedicated regression tests.
- [ ] **Live acceptance BLOCKED (not PASS):** from this agent environment TCP
  access to `172.17.0.24:8091` and `:9090` failed, and public FastAPI Cloud
  hostname resolution failed. These observations do not establish whether the
  corresponding services are healthy inside the homelab.
- [ ] Prove from inside the **FastAPI TrueNAS container** that
  `HOMELAB_PROMETHEUS_URL=http://172.17.0.24:9090` is configured, that
  `/-/ready` and `/api/v1/query` respond, and that the recording rules
  `nabla:telemetry:gatus_up`, `nabla:service:synthetic_probe_success`,
  `nabla:service:synthetic_probe_duration_seconds`, and
  `nabla:service:synthetic_availability_ratio_5m` contain fresh, correctly
  labeled series. Missing rules are telemetry gaps, never service DOWN.
- [ ] Run the existing cached `/api/health-board` and diagnostic comparison
  against real internal service IDs. Record matched/mismatched/missing counts,
  freshness and any stale cache. Preserve FastAPI Cloud public outside-in
  evidence as an independent source; do not launch parallel provider fan-out.
- [ ] Compare runtime identifiers with the authoritative `nabla-compose`
  catalog. Never join services by display name or silently downgrade public
  protection outcomes when Gatus is green.
- [ ] Validate the focused synthetic comparison and platform-metrics tests,
  then run local Ruff and quality gate on the **new HEAD**. No green CI claim
  without that proof.
- [ ] **OpenRAG decision:** inventory existing OpenRAG/Langflow/embedding
  endpoints, durable storage, authentication and tenant boundaries before
  implementing a separate persistent `VectorStore`. Prefer an OpenRAG
  adapter behind an injected `VectorStore` protocol if it meets those
  contracts; do not introduce a second mutable vector index by default.
  Optional RAG outage must remain independent of core health.

## Operating constraints

- Python 3.13 + `uv` are the supported Python/tooling baseline.
- FastAPI Cloud is the canonical production runtime.
- Vercel Git deployment is disabled and must not be a merge gate.
- GitHub Actions capacity is constrained: prefer deterministic local validation.
- Optional homelab integrations must not become application liveness dependencies.
- Preserve observer independence: FastAPI Cloud is the outside-in observer for
  public exposure/security, while Gatus/Prometheus on TrueNAS are inside-out
  homelab observers and must not replace that external vantage point.
- Never weaken TLS, authentication, timeouts, cache/circuit breakers or rate
  limits merely to make health status appear green.
- Close a roadmap item only with an explicit acceptance proof.

## CURRENT DELIVERY ORDER — finish service stabilization and migrations (2026-10-11)

Operator priority supersedes the ordering of technical-debt sections below.
The controlling source of homelab service state is
`nabla-compose/docs/roadmap.md`; `fastapi-sample` owns outside-in
health/security evidence and its consumer migration.

1. **Resolve service regressions before feature work:** Gatus (internal),
    pfSense/CrowdSec, then missing acceptance for Sentry, Scrutiny, DSOMM,
    Pi-hole, Pyroscope and TrueNAS/Talos. Do not mark an external optional
    integration DOWN merely because evidence is unavailable; retain explicit
    warning/unknown state.
2. **Finish active secrets migrations** in `nabla-compose` one service at a time,
    with runtime identity, consumer, permissions, Vaultwarden recovery and
    Backstage metadata. FastAPI Cloud does not require direct exposure to
    TrueNAS private secrets.
3. **Prepare then execute a direct catalog-v2 cutover:** reconcile topology,
    entities, BIA criticality and exposure policies in `nabla-compose`,
    then migrate `fastapi-sample` and `nabla-site-alban` consumers at a common
    reviewed revision. Avoid a permanent v1/v2 compatibility shim; preserve a
    tested rollback until runtime, outside-in security and reboot checks pass.
4. **Validate observer separation:** FastAPI Cloud remains the independent
    external DNS/TLS/HTTP/Cloudflare Access/WAN vantage; Gatus/Prometheus on
    TrueNAS provide internal evidence. Never infer public reachability from
    internal-only availability.
5. **Finish P1 only where migration-blocking:** app lifecycle and HTTP resource
    changes that fix proven service failures. Defer Dagger PoC, synthetic schema
    experimentation, output optimization and optional RAG features until runtime
    and cutover are accepted.

**Quality-gate policy:** keep all safety checks intact and run targeted local
tests on each change. The complete local publication gate and required
SAST/BetterLeaks/Playwright/ZAP checks remain **before-merge** requirements,
not the principal delivery workstream. Record unavailable checks as NOT RUN;
no auto-merge and no automatic infrastructure restarts.

## CURRENT FASTAPI-SAMPLE DELIVERY SLICE — six workstreams (2026-10-11)

Only the following workstreams are in the immediate implementation scope.
Keep `nabla-compose` authoritative for declared service identities and
exposure, and retain FastAPI Cloud as an **independent public** observer.

1. **Secure diagnostic retention:** opt-in logs may contain scanner output,
    tokens or internal URLs. Require a non-symlink, private, current-user-owned
    destination; keep original check exit codes. Do not retain successful logs.
    - [x] Enforce directory owner as well as access-mode checks, with a
      simulated foreign-owner regression test.
    - [ ] Validate these checks with the complete local test module and
      threat-model unsafe parent directories/races before enabling retention
      on an operator workstation.
2. **pfSense / TrueNAS / Cloudflare:** keep authenticated and unauthenticated
    evidence distinct; 401/403 policy denials are not transport DOWN, while an
    unexpected 2xx anonymous response is a security failure. Preserve the
    bounded pfSense preflight and Cloudflare unknown/warning behavior. Complete
    TrueNAS observer and public Cloudflare Access acceptance from both vantages
    without reusing LAN results as Internet evidence.
3. **Canonical catalog:** prepare consumers for a *direct, coordinated*
    `nabla-compose` v2 cutover. Validate stable full entity refs, BIA
    criticality, desired exposure, relations, revision/provenance and packaged
    fallback before the cutover. Do not delete legacy catalogs or infer runtime
    availability from declarative `active` fields. Do not create a second
    source of truth in FastAPI.
4. **Gatus / Prometheus:** compare only internal generic probes to TrueNAS
    Gatus; public Cloudflare/DNS/TLS/WAN results remain in FastAPI Cloud.
    Require Prometheus query evidence and actual Gatus HTTP/history recovery;
    absent internal evidence should be a warning rather than an invented green.
5. **Application factory / lifespan:** inventory import-time Postgres, Redis,
    HTTPX and optional AI initialization, then introduce a minimal hermetic
    factory and lifespan-owned shared clients incrementally. Prevent startup
    failure of optional homelab integrations from taking down core liveness.
6. **Synthetic Open Schema:** generate from the `nabla-compose` catalog,
    validate schema and test an external DNS/TLS/HTTP sample with the official
    runner. Retain explicit Cloudflare anonymous default-deny, service-token
    authorization and WAN/SNI evidence; adopt only if net code and contract
    complexity actually decrease.

**Delivery order:** diagnostic security and evidence contracts → catalog
consumer readiness → Gatus/Prometheus reconciliation → incremental lifecycle
isolation → SOS runner acceptance. Perform targeted tests for each change;
full SAST, BetterLeaks, Playwright, ZAP and publication proof remain required
before merge. No automatic merge or live appliance mutation.

## P0 — production security and privacy

- [ ] Set `DEBUG=false` in FastAPI Cloud and prove unexpected exceptions no
  longer expose tracebacks.
  - [x] Enforce `DEBUG=false` in the declarative Cloud deploy workflow and
    suppress Starlette debug tracebacks when any Cloud marker or configured
    `APP_DOMAIN` identifies FastAPI Cloud, even if `FASTAPI_ENV=development`
    conflicts with that evidence; cover both with offline regression tests.
  - [ ] After the next authorized production deployment, verify the effective
    remote environment and a controlled non-sensitive HTTP 500 response;
    do not trigger an exception on the public endpoint solely for this check.
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

### P0 Prometheus telemetry reconciliation (2026-10-11)

- [x] Cross-check Prometheus scrape jobs and recording-rule names with the fixed FastAPI query contract: Gatus synthetic samples are already read through `nabla:telemetry:gatus_up` and `nabla:service:synthetic_*` rules.
- [x] Add optional, bounded recording rules for PostgreSQL/Redis exporter availability, `pg_up`/`redis_up`, FastAPI, Pyroscope, Alertmanager and the existing pfSense memory ratio (coordinated with nabla-compose #253).
- [x] Expose those signals in the cached `platform_metrics.summary.optional_exporters` without adding a second Prometheus query or changing mandatory telemetry classification.
- [ ] Validate recording-rule loading and actual samples from TrueNAS Prometheus; a declared scrape does **not** establish that an exporter is running or reachable. Keep missing optional series unknown, never DOWN.
- [ ] Evaluate Cloudflare **control-plane API metrics** independently; there is currently no verified Cloudflare Prometheus exporter/scrape job. Do not synthesize `cloudflare_up` or conflate Cloudflare API data with Prometheus evidence.
- [ ] Inventory other declared jobs (Kafka, ClickHouse, OpenSearch, Loki, Alloy, Tempo, Mimir, Keycloak, CrowdSec, DNS, HAProxy) and prioritize stable recording rules by operator value before extending the fixed contract.

### Prometheus service telemetry follow-up (2026-10-11)

- [x] Extend the existing **single fixed PromQL query** with `nabla:telemetry:service_exporter_up`, a job-labeled recording rule defined in `nabla-compose`; consume only an explicit allowlist, excluding arbitrary labels and cardinality expansion.
- [x] Cover Kafka, ClickHouse, OpenSearch, observability stack, Keycloak, CrowdSec, Pi-hole, HAProxy, n8n and Docling as optional exporter/target scrape evidence.
- [ ] On TrueNAS, prove Prometheus rule-load success, per-job coverage and fresh samples. Exporter scrape `up=0` denotes unavailable *telemetry*, not automatically a failed application.
- [ ] Confirm whether a real Cloudflare exporter exists: the job label being configured in a rule is **not** evidence of a running exporter. Preserve the separate Cloudflare API observer and authenticated Access checks.

### Duplicate exporter-series contract (2026-10-11)

- [x] When the bounded Prometheus vector contains multiple `nabla:telemetry:service_exporter_up` samples for the same allowed job, aggregate conservatively using the minimum 0/1 value. An `up=0` observation cannot be concealed by result ordering.
- [x] Add regression cases for both orders of conflicting samples; preserve separation between exporter telemetry health and application availability.
- [ ] On TrueNAS, compare source labels / target duplication if this diagnostic actually occurs; do not silently rewrite scrape jobs or restart Prometheus.
- [ ] Run focused tests and exact-HEAD local publication quality checks when a trustworthy checkout is available; no CI checks have been bypassed or declared green.

### Gatus Prometheus defensive aggregation (2026-10-12)

- [x] Reject unsupported synthetic probe types and out-of-domain values; only TCP/HTTP/HTTPS are used for internal comparison.
- [x] Resolve conflicting Gatus up/success/availability samples conservatively (`min`) and duplicate durations using the worst observed time (`max`) without changing outside-in health.
- [x] Add a regression test covering contradictory metrics, invalid success/duration and unknown probe types.
- [ ] Execute exact-HEAD tests and confirm that recording rules load and expected samples appear on TrueNAS. No runtime health claim is inferred from these code changes.

### Gatus label and cardinality guardrails (2026-10-12)

- [x] Validate service IDs before including them in cached Prometheus results; accept only bounded lowercase catalogue-style identifiers and recognized TCP/HTTP/HTTPS types.
- [x] Cap the number of distinct service IDs at 256 and explicitly flag `synthetic_probes.truncated`; a truncated inventory is `telemetry_unavailable` and cannot authorize internal delegation.
- [x] Add regression coverage for malformed labels, unexpected values and series cardinality.
- [ ] Validate the real TrueNAS catalogue ID space and Prometheus samples, then adjust the contract through reviewed tests if an authorized service ID does not match. Complete exact-HEAD tests before merge.

### Gatus raw fallback conflict handling (2026-10-12)

- [x] Resolve duplicate `up{job="gatus"}` samples with conservative 0/1 aggregation, regardless of result order; never let an available target conceal a failing sibling target.
- [x] Add targeted regression tests for both sample orders and preserve recording-rule precedence.
- [ ] Test real Prometheus scrape target multiplicity and fix duplicate targets at the authoritative `nabla-compose` source if discovered. Record actual series freshness and validation output in the grouped TrueNAS acceptance campaign.

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
- [x] Define the provisional fixed-cardinality pfSense control-plane target:
  successful `system.version` preflight p95 <2.0 s over 30 minutes; keep the
  separate 2.5 s per-request protection threshold and do not claim the target is
  met until a sustained TrueNAS baseline is collected.
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
    - [x] Export fixed-cardinality pfREST request-rate and in-flight metrics for
      `preflight|deep`; slow/auth-rejected preflights emit no deep request and
      normal posture refreshes remain one preflight plus three bounded deep reads.
    - [x] Exercise the deep-read semaphore with more candidate reads than the
      production fan-out and prove observed concurrency never exceeds 2.
    - [x] Add a Prometheus-only baseline collector for p95/p99, protective
      skips, request counts and in-flight work; it performs zero direct pfREST
      calls and keeps threshold changes blocked until appliance evidence is
      correlated.
    - [ ] Collect a sustained TrueNAS-runtime baseline and correlate p95/p99,
      skip rate, provider in-flight work and pfSense CPU/RAM/PHP-FPM/FastCGI
      evidence before changing the 2.5 s threshold.
  - [ ] Correlate bounded pfSense nginx/pfREST evidence with the passive
    `Nabla-Probe-Origin`, `Nabla-Probe-Name`, `Nabla-Probe-Request-ID`
    and W3C trace context fields, without logging API keys or treating probe
    metadata as an authorization signal.
    - [x] Generate correlation metadata per HTTP request rather than once per
      shared client; keep `X-API-Key` separate from those headers.
    - [x] Emit bounded client-side DEBUG correlation and expose the request ID
      from the redacted auth-smoke CLI without logging credentials.
    - [ ] Implement the bounded generated-nginx/pfREST log capture in
      `nabla-compose`, then prove one TrueNAS request ID across client/server
      evidence without exposing secrets.
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
  path for pfSense API evidence. FastAPI Cloud keeps the dedicated authenticated
  posture/security probes enabled for outside-in evidence, with fail-fast on the
  first HTTP 401 and `PFSENSE_AUTHENTICATED_PROBES_ENABLED=false` retained only
  as an emergency kill-switch.
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

## P0 — deterministic offline agent validation

- [ ] **Exact-HEAD materialization:** acquire the approved commit SHA through a
  verified GitHub connector or an existing local checkout/cache when DNS blocks
  `git clone`. Accept downloaded archives only when the transport is trusted,
  the commit identity is established independently, and repository content is
  compared against the intended SHA. An archive URL alone is not proof.
  - [x] Add the offline cached-Git snapshot script and its acceptance tests;
    documented in [local-first-source-snapshot.md](local-first-source-snapshot.md).
    This is an available fallback, not proof of the current PR HEAD.
  - [x] Allow an optional comparison base and fail closed when it is missing or
    not an ancestor of the requested HEAD. Isolated L1 execution proves the
    Bash syntax, positive ancestry path and negative non-ancestor path; the
    complete exact-HEAD repository gate remains NOT RUN until a full checkout
    of the current PR HEAD is available.
- [x] Harden the post-reboot diagnostic against a boolean Gatus `service_count` and unknown/missing board state; regression tests added. Exact-HEAD pytest and runtime acceptance remain **NOT RUN**, not PASS.
- [ ] **Run gates against the same source tree:** execute `bash -n`, targeted
  pytest, Ruff, canonical pre-commit, BetterLeaks and the repository publication
  gate on that exact tree. Report each missing dependency or unavailable tool
  separately; never treat absent GitHub statuses as successful checks.
- [ ] **Preserve security coverage:** keep SAST and BetterLeaks in the canonical
  security gate, and retain Playwright and ZAP where their integration/E2E
  execution environments are available. Do not silently disable or replace
  these checks with static assertions about workflow files.
- [ ] **Bound agent transcripts, not evidence:** display concise failing
  summaries while retaining full logs as local artifacts. Reuse proven results
  only when HEAD, comparison base, toolchain and relevant environment match.
- [ ] **Publication acceptance:** attach a concise validation matrix to the PR
  with exact HEAD and PASS/FAIL/NOT RUN states. Keep the PR Draft and do not
  merge automatically until all required gates have actual evidence.

## P1 — dependency automation and CI governance

- [ ] Introduce **Dagger CI** as the portable local-first execution layer, not as
  a second CI authority.
  - [x] Expose `just p1-parity-native` as the native Ruff + targeted
    local-first contract baseline, without modifying CI or security hooks.
    This is L1 targeted evidence only, not full publication acceptance;
    capture exact SHA and timings when an appropriate local checkout exists.
  - [ ] Benchmark native baseline and Dagger against the same SHA,
    dependency cache state and input files; record wall time, exit status,
    tool versions and missing checks. Reject a performance-only result
    without equivalent assertions and scanner coverage.
  - [x] Add a fail-closed, read-only `just p1-dagger-preflight`
    prerequisite checker (tool availability, module configuration and checked-in
    lockfile) with offline regression tests. The probe is not a Dagger pipeline
    and is not L3 evidence.
  - [ ] Pin the Dagger CLI/Engine and initialize a Python SDK module; the
    official Dagger documentation is currently on the 1.0 beta line, so start
    with a bounded pilot rather than rewriting every workflow at once.
  - [ ] Model the deterministic local gates first: targeted/full pytest, Ruff
    format/lint, py_compile/contract checks and repository generators. Keep
    Betterleaks and other security scanners explicit and pinned; do not weaken a
    scanner merely because it is harder to containerize.
  - [ ] Make the existing exact-HEAD archive/snapshot materialization usable as
    Dagger input so validation remains possible when `git clone` or DNS is
    unavailable.
  - [ ] Expose the same Dagger functions through `just` locally and a thin
    GitHub Actions launcher remotely; pipeline logic must live in Dagger rather
    than be duplicated in Actions YAML.
  - [ ] Keep production credentials out of cacheable Dagger layers and pass
    secrets only to the minimum functions that require them.
  - [ ] Accept the pilot only when the same SHA produces equivalent local and CI
    results and cached reruns reduce local feedback time without hiding stale
    generated output.
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

## P1 — dual-vantage probes and code reduction

The two observers answer different questions and must remain independent:

```text
FastAPI Cloud (outside homelab)        TrueNAS (inside homelab)
        |                                      |
  public DNS/TLS/HTTP/Access                 Gatus
        |                                      |
  Internet -> Cloudflare/pfSense             LAN/services
        |                                      |
  exposure + security evidence               internal health
```

- [x] Classify Gatus/Prometheus as an **internal TrueNAS observer**. Its 45/45
  active-monitor coverage is useful for LAN/application health but cannot prove
  that a service is reachable or correctly protected from the public Internet.
- [x] Preserve the FastAPI Cloud probes as the canonical **outside-in** evidence
  for public DNS, TLS, HTTP status, Cloudflare Access/service-token behavior,
  HAProxy/WAN exposure and externally visible application failures.
- [x] Restrict the Gatus shadow comparison/delegation diagnostic to generic
  **internal** probes. Public FastAPI Cloud results are deliberately not compared
  for equality with Gatus because a difference may be the signal being sought.
  HTTP Gatus evidence is treated as stronger application evidence, not as a
  TCP-transport mismatch.
- [ ] Prove `HOMELAB_PROMETHEUS_URL=http://172.17.0.24:9090` on the TrueNAS
  observer and collect internal comparison evidence before deciding whether any
  in-process TrueNAS TCP fan-out can be delegated to Gatus.
- [ ] Keep all outside-in public probes embedded in FastAPI Cloud unless another
  probe engine is deployed in an **independent external failure domain**.
  A second Gatus or Prometheus Blackbox Exporter instance outside the homelab
  could qualify; the current TrueNAS instances do not.
- [ ] Reduce the external Python probe implementation with mature libraries
  rather than replacing the external observer:
  - keep **HTTPX** for HTTP/HTTPS and explicit connect/read/write/pool timeouts;
  - [x] use **dnspython asyncresolver** for public A/AAAA evidence; remove
    threaded `socket.getaddrinfo` and custom `/etc/resolv.conf` parsing while
    preserving bounded resolver identity, latency and DNS failure evidence;
  - [x] use **AnyIO** `connect_tcp` + cancel scopes for generic internal TCP
    probes instead of `asyncio.open_connection` + `wait_for`;
  - [ ] evaluate the same AnyIO transport primitives for the specialized
    TrueNAS TCP/TLS diagnostic only after preserving its SNI, certificate,
    cipher and hostname-verification evidence contract;
  - retain stdlib `ssl` for certificate/session facts; use `cryptography`
    only if richer X.509 parsing is actually required;
  - do **not** add generic automatic retries to health probes: retries distort
    latency and can amplify load on degraded pfSense/TrueNAS paths.
- [ ] Evaluate **Synthetic Open Schema (SOS)** as a generated contract, not as a
  new source of truth.
  - [x] POC in `nabla-compose`: generate one runner-compatible v1 YAML per
    DnsCheck/TlsCheck/HttpCheck from the current public-exposure catalogue.
    The current snapshot produces **78 resources for 26 public HTTPS services**
    (26 DNS + 26 TLS + 26 HTTP); 25 protected HTTP checks reference only
    `${CF_ACCESS_CLIENT_ID}` / `${CF_ACCESS_CLIENT_SECRET}` placeholders.
    Generation/test commands are `just sos-generate` / `just sos-test`.
  - [ ] Move public exposure intent from transitional
    `catalog/homelab-services.json` into the canonical catalog-v2 authority,
    then switch the SOS generator before deleting the legacy file.
  - [ ] Validate every generated resource with the official
    `synthetic-open-schema-model` and execute a representative outside-in
    subset with the official async Python runner.
  - [ ] Measure deletion after a runner-adapter POC. Current minimum candidate
    surface is about **198 production lines** (96-line DNS module plus the
    39-line generic HTTP error assertion and 63-line HTTP executor), before any
    additional batch/orchestration deletion; matching tests should shrink too.
    Cloudflare anonymous default-deny, service-token policy, warning-state
    classification and WAN/SNI attribution remain explicit adapters.
  - [ ] Adopt the runner only if the net production/test LOC and maintenance
    burden decrease and result semantics remain at least as precise as today.
- [ ] Do not adopt young all-in-one libraries such as PyUptimeKit/pyhealthcheck
  until maturity, async behavior, security maintenance and Python 3.13 support
  are proven; current bespoke semantics for Cloudflare Access and security
  attribution would still need adapters.
- [ ] After internal delegation is proven, delete only the TrueNAS/internal
  generic fan-out code made redundant by Gatus. Do **not** delete the external
  public probe path, DNS/TLS attribution or Cloudflare Access logic.
- [x] Factor shared Prometheus vector parsing/query helpers so platform,
  topology and diagnostic consumers do not maintain parallel HTTP API parsers.
- [ ] Remove the `# noqa: C901` exemptions added (2026-10-14) so repo-wide
  `ruff check .` passes: split `get_or_refresh_probe` (complexity 28),
  `append_truenas_api_stages` (15), `TrueNASClient.health_snapshot` (14),
  `_query_fixed_metrics` (17, from #338), `compare_internal_probe_evidence` (13),
  `_security_filter_observations` (12),
  `public_topology_payload`, `check_pfsense_api` and the diagnose script
  `print_table` (11) below the McCabe limit of 10.
- [x] Make the agent shell tooling portable to macOS/BSD userland
  (`mv -T`, `stat -c`, `install -d` chmod and suffixed `mktemp` fallbacks in
  `agent-source-snapshot.sh` and the quality-failure log retention).
- [ ] Prove the GNU branch of those shell fallbacks on the Linux CI runner:
  acceptance is a green pytest job for the first PR carrying the change
  (only validated locally on macOS so far).
- [x] Reconcile `test_agent_quality_gate_wraps_tests_and_canonical_gate` with
  the `QUALITY_FIX_PASSES` help text (`default: 6, capped at 20`).
- [x] Make `mise.toml` the single toolchain version source: `.tool-versions`
  and `.nvmrc` removed; CI reads `tools.node` from `mise.toml`.

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

These items are not complete until their acceptance checks run against the
actual repository HEAD. Do not treat this breakdown as implementation evidence.

- [ ] **Notes contract normalization**: inventory current API models, database
  columns, callers, migrations and authorization tests before changing storage.
  - [ ] Make `completed` a real boolean across request/response, persistence and
    serialization; retain backwards compatibility only when consumers require it.
  - [ ] Use timezone-aware UTC timestamps and test input/output normalization.
  - [ ] Define typed read/delete responses, explicit 404/403 behavior and
    authorization-preserving CRUD tests.
  - [ ] Verify database migration and roundtrip integration in an isolated DB;
    do not rewrite production rows without reversible migration evidence.
- [ ] **RAG concurrency and persistence**: replace global mutable vector state
  with an injected `VectorStore` protocol; identify all readers and writers
  before choosing a backend.
  - [ ] Test concurrent indexing/search, lifecycle shutdown, persistence across
    application restarts, and tenant/data isolation.
  - [ ] Keep failures in the optional RAG backend out of core app liveness.
- [ ] **SearXNG integration**: first establish the authoritative Compose service
  and its health/access policy in `nabla-compose`; then add an opt-in adapter
  with explicit timeout, SSRF protection, credential redaction and offline tests.
- [ ] **MCP SDK and pfSense**: pin/review SDK API changes; retain private
  transport, least-privilege identity, bounded tool fan-out, request auditing,
  and deny-by-default authorization regression tests.
- [ ] **Compose/Docker consolidation**: current references indicate
  `Dockerfile-pipenv` and `Dockerfile-poetry` may be orphaned, whereas
  `docker-compose.yml` retains legacy/dev PostgreSQL and Redis consumers.
  - [ ] Audit references across Makefile, justfile, mise, Helm and workflows.
  - [ ] Build/smoke canonical `Dockerfile` + `docker-compose.yaml` locally.
  - [ ] Remove obsolete files only after reference and rollback checks pass.
- [ ] **P2 merge evidence**: for every changed contract, record targeted test,
  offline quality gate, SAST/BetterLeaks evidence and any Playwright/ZAP tests
  appropriate to its exposed endpoints. Mark unavailable checks NOT RUN,
  never PASS. No automatic merge.

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
