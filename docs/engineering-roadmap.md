# Engineering roadmap — active, acceptance-driven

**Version : 2026-10-20.** Keep only unresolved deliverables and validation
conditions here. Do not append completed PR narratives.
For long-tail unchecked tasks use the [on-demand backlog](engineering-backlog.md);
it is **not** an automatically approved roadmap. Historical implementation
notes remain in [Git history](https://github.com/AlbanAndrieu/fastapi-sample/blob/594d51d64efdd5274d2ba42a9cb09551b6d57d46/docs/engineering-roadmap.md).

## P0 — CI : tracker unique `master-red` (#355)

- **Implémenté, à valider** : un seul commentaire d'état du bot dans #355, sans nouvelle issue par SHA, sans PR brouillon vide, sans modification du titre, du corps ni des labels ; conservation des preuves des 32 anciens doublons dans GitHub. Script canonique : `scripts/ci/master_red_issue.py`.
- **Protection humaine** : une modification manuelle du titre, du corps, des labels, de l'état **ou un commentaire humain avant/après inscription** interdit toute mutation automatique future. #355 a été renommée manuellement : elle ne doit jamais être clôturée/réouverte par le bot, même après deux succès. Seule une issue sans intervention humaine peut bénéficier de la clôture après deux numéros de runs `master` consécutifs tous verts.
- [ ] Exécuter `python3 -m unittest tests.unit.test_master_red_issue -v` sur le HEAD exact et la gate locale ; aucune preuve de réussite CI globale à inférer.
- [ ] Après déploiement sur `master`, constater deux runs complets consécutifs (CodeQL/ZAP `skipped` acceptables **uniquement** si non requis par la classification), et vérifier les causes racines Python/Smoke. Ne pas provoquer d'échec artificiel.

## P0 — public/private observability boundary (PR #353 / issue #352)
- [ ] Audit every live HTTP/ASGI WebSocket mount, docs/OpenAPI, MCP, admin,
  health and HTML route on the exact deployed FastAPI SHA. Validate access
  policy classification, missing credentials and negative bypass tests.
- [ ] Verify signed Cloudflare Access JWT (RS256/JWKS, `iss`, `aud`,
  expiration and exact human identity); Service Token and owner policies
  remain distinct. Keep runtime strict mode disabled until all consumers
  use the public allowlisted DTO `/api/public-homelab/v1`.
- [ ] Coordinate removal of sensitive public static/site API projections in
  `nabla-site-alban`; only then deploy `ops.albandrieu.com` through
  private Traefik/Tunnel/Access in `nabla-compose`. Prove MFA, no origin
  bypass and rollback. Keycloak is not a P0 dependency.

## P0 — scanning and LAN-only DefectDojo
- [ ] Validate the weekly/manual `Docker CI` Trivy JSON artifact plus SARIF
  conversion from **one** scan. Check GH run SHA/event, exact ZIP, no secret
  evidence, size and expected product/engagement before enabling import.
- [ ] Keep PR Betterleaks and Trivy Critical/secret blocking; expand SCA,
  Semgrep, CodeQL, Nuclei and ZAP only at approved cost-aware cadence.
  Do not automatically publish sensitive DAST/PII/SBOM on GitHub.
- [ ] Test GitHub App `Actions:read` least privilege, LAN HTTPS/SNI to
  `defectdojo.int.albandrieu.com`, bot RBAC denied outside its engagement,
  Vaultwarden initialization and Celery import+dedup. No public DefectDojo.

## P1 — FastAPI staging → TrueNAS LiteLLM → workstation Qwen (2026-10-20)
- [x] Fail closed if LITELLM_URL is set without a virtual key; unit tests demonstrate `DEFAULT_CHAT_MODEL=fastapi-qwen` uses the TrueNAS gateway and does not route through Azure/OpenAI directly.
- [x] `nabla-compose` PR #263 declares the staging URL/model and routes `fastapi-qwen` → workstation `qwen`, with separate upstream/downstream key policy and an 8 USD nonresetting cap (more restrictive than 10 EUR target at usual exchange rates).
- [ ] Actually generate **both** scoped keys on trusted endpoints, store through Vaultwarden, verify both DBs and nonzero spend, test function calling/negative fallback, and deploy TrueNAS staging. These runtime operations are NOT_RUN.
- [ ] Cloud `fastapi-sample.fastapicloud.dev` is not connected: no authenticated transport to private LAN has been established. Do not set a private RFC1918 LiteLLM URL on cloud. Canonical [runbook in nabla-compose](https://github.com/AlbanAndrieu/nabla-compose/blob/docs/private-homelab-observability-boundary-20261018/docs/runbooks/fastapi-sample-litellm.md).

## P1 — Per-service Prometheus/Gatus and explicit fan-out coverage (2026-10-20)
- [x] Reuse the **existing** read-only `/api/health-board` fixed-query Prometheus snapshot for service-card badges; show Gatus observation, Prometheus scrape, and explicit job for PostgreSQL/pfSense/other mapped exporters. Show PostgreSQL `pg_up` separately from exporter `up`.
- [x] Explain eligible probe slots versus catalog services without targets, current-wave rotation, stale/unobserved evidence and LAN disabled; do not report missing evidence as a service outage.
- [ ] Deploy the corresponding `nabla-compose` Gatus labels for pfSense/PostgreSQL/TrueNAS and deduplicated Prometheus recording rules. Verify with `scripts/truenas/diagnose-prometheus-targets.sh` and `scripts/prometheus/audit-telemetry-coverage.py`; confirm exact service ID recording series and both exporter job states. Repository declarations are not runtime evidence.
- [ ] Validate service-card presentation behind Cloudflare Access after staging deploy and measure 3+ full rotating windows; retain external probes for outside-in context. A catalog with >12 eligible slots per scope cannot reach 100% on a single 30-second refresh.

## P1 — health, topology and runtime acceptance
- [ ] After an approved deployment, compare Garage external/internal probe
  phases over three cycles, unexpected admin Tunnel exposure and WAN NAT
  reflection. Separate `unknown` from an actually failed health check.
- [ ] Reconcile canonical `nabla-compose` topology IDs and Gatus telemetry
  from TrueNAS/Talos/Kubernetes/Prometheus; preserve cloud outside-in probes.
- [ ] Verify changed runtime health and security posture with LAN evidence.
  Retain incident-specific symptoms, commands and recurrence criteria in
  [incidents.md](incidents.md) or the appropriate infrastructure runbook.

## P1 — local-first quality and reduced agent context
- [ ] Run focused pytest, workflow YAML validation and the repository's
  deterministic `scripts/agent-quality-gate.sh --fix` followed by clean
  `scripts/agent-publish.sh` on the exact HEAD. Report missing tools as
  **NOT_RUN**, never success. Do not spend CI credits just for formatting.
- [ ] Re-evaluate any item from the legacy backlog **before** restoring it
  to this roadmap. Retire completed/obsolete checklists rather than
  accumulating date-stamped status paragraphs.
- [ ] Evaluate Dagger only if it demonstrably improves measured local/CI
  parity without duplicate pipeline maintenance.
- [ ] **actionlint + zizmor** : exécutés en pre-commit et dans le job
  `preflight` de `python.yml` (`--all-files`, configuration
  `.github/zizmor.yml`, `.github/actionlint.yaml`). Résidus :
  - appels locaux passés à la syntaxe `$/` (audit zizmor `self-repository`
    actif) ; actionlint 1.7.12 ne la connaît pas : ses deux messages sont
    ignorés dans `.github/actionlint.yaml` (même correctif que
    wakam/Wakam#4131), ce qui le prive aussi de la vérification des
    `inputs`/`outputs` de ces workflows réutilisables. Preuve de clôture :
    actionlint accepte `$/…` → supprimer l'ignore ;
  - **NOT_RUN** : premier run GitHub d'un `uses: $/.github/workflows/…`
    (syntaxe récente) et de la nouvelle étape CI (local-first).
  - `mirrors-prettier` remplacé par `rbubley/mirrors-prettier` v3.9.10 ;
    reformatage cosmétique accepté, `secrets-enc.yaml` (SOPS) exclu.
- [ ] **Renommage** `production-smoke.yml` → `master-smoke.yml` (id de job
  `production-smoke` et `name: Production Smoke` conservés pour ne casser
  ni `needs` ni les noms de checks). Preuve : règles de protection de
  branche vérifiées, puis un appel vert `deploy.yml` → `master-smoke.yml`.
- [ ] **Tests #353 corrigés** (23 échecs hérités) : client de test
  authentifié par clés factices (routes privées fail-closed), tests
  DefectDojo alignés sur l'API `private_file`/`validate_format`, contrats
  texte rendus robustes au reformatage ruff, fixture master-red sans
  historique manuel par défaut. Preuve : `agent-publish.sh` vert au HEAD.

## References and finish condition
- [Incident register](incidents.md): preserve unique diagnostic facts and
  recovery procedures that cannot be inferred from code.
- [Long-tail backlog](engineering-backlog.md): historical unchecked tasks
  requiring current verification.
- `AGENTS.md` / `.agents/skills/local-first-quality/SKILL.md`:
  source of truth for validation/evidence policy.
- No merge/deployment without instruction; status = PASS/FAIL/NOT_RUN
  linked to the exact commit and tested environment.
