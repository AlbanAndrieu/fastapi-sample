# Roadmap active — FastAPI Sample

**Consolidée le 30 octobre 2026.** Document canonique des **travaux non
acceptés**. Les correctifs terminés sont dans le code/tests et les PR ;
les constats datés dans [le registre d'incidents](incidents.md), l'historique
dans [l'archive du 29 octobre](archive/2026-10-29/engineering-roadmap-before-consolidation.md),
et les tâches anciennes non requalifiées dans
[le backlog historique](engineering-backlog.md).

**Règle de preuve :** `CODED` = écrit dans Git ; `TESTED` = commande réussie
sur un SHA précis ; `DEPLOYED` = SHA/image reconnu sur le runtime ;
`ACCEPTED` = comportement vérifié sur ce runtime par le bon observateur.
`NOT_RUN`, `UNVERIFIED`, HTTP 401/403 et une PR fusionnée ne sont **pas** des
preuves de santé ou d'acceptation.

## Situation actuelle

| Surface | Preuve disponible | Blocage / prochaine vérification |
| --- | --- | --- |
| Cloud public | L'opérateur confirme que `/api?ui_safe=1` fonctionne | `/api?ui_full=1` reste sur Loading ; aucune recette Chromium récente du SHA déployé |
| OWNER mobile | `/api/ui/session` → `authenticated=false, readOnlyDiagnostics=true` ; direct LAN `:8091/api` joignable | `Unlock diagnostics` absent sur HTTPS ; session OWNER et source proxy non acceptées |
| PR FastAPI [#382](https://github.com/AlbanAndrieu/fastapi-sample/pull/382) | Draft ; patch UI/OWNER et diagnostics/agent local-first **codés** ; tests isolés précédemment rapportés | Tests Node/Python du **HEAD complet**, quality gate L2/L3 et navigation réelle `NOT_RUN` |
| PR FastAPI [#380](https://github.com/AlbanAndrieu/fastapi-sample/pull/380) / [#381](https://github.com/AlbanAndrieu/fastapi-sample/pull/381) | Fusionnées ; anti-boucle et démarrage public léger dans Git | Aucun SHA/image Cloud ou TrueNAS actuel vérifié |
| TrueNAS Docker | Déploiement historique `fa13c08d` accepté 6/6 ; tentative `0266f20d` échouée en étape 3/6 | Classifier l'échec Docker privé avant un nouveau build |
| Gatus | Dernière observation historique : 85 sondes déclarées ; 61 UP / 24 DOWN au 26/10 | Couverture, causes et fraîcheur **non revalidées** ; `gatus_up=1` est insuffisant |
| Prometheus `fastapi_sample` | Scrape auparavant HTTP 401 ; configuration de clé dédiée signalée | Confirmer scrape authentifié `up=1`, sans exposer la clé ni lever l'auth anonyme |

## P0 — Rendre le dashboard Cloud interactif et publiable

- [x] **CODED (#382) :** `ui_full=1` importe le module riche volontairement ;
  patch de réconciliation des lignes et de mutations `hidden` idempotentes.
  Le catalogue public léger et `ui_safe=1` sont préservés.
- [x] **CODED (#382) :** sonde Chromium distinguant
  `main_thread_unresponsive`, `ui_loading_without_content`,
  `http_access_restricted` et `sampled`.
- [ ] **L1 :** exécuter `just ui-quick` et les tests Python affectés
  sur un checkout isolé au HEAD exact de #382 ; corriger le premier
  échec reproductible. Le résultat réel actuel est `NOT_RUN`.
- [ ] **L2/L3 :** exécuter `scripts/agent-quality-gate.sh --fix`,
  examiner le diff et obtenir la preuve `scripts/agent-publish.sh`
  sur un HEAD propre ; ne pas utiliser GitHub Actions comme boucle.
- [ ] **Navigateur Cloud :** comparer public, safe et riche sous Chromium
  depuis un client autorisé ; relever les lignes, erreurs, temps de blocage
  et premier module fautif. Vérifier le SHA réellement déployé.
- [ ] **Publication Cloud :** soumettre le correctif à revue ; publier
  seulement via le chemin de déploiement FastAPI Cloud autorisé et
  vérifier les quatre modes sur la nouvelle version. **Pas de déploiement
  automatique par l'agent.**

**Done P0 :** `ui_full=1` ne reste pas sur Loading ; cartes et interactions
répondent ; le mode public demeure rapide et les refus HTTP sont classés
comme tels. La cause DOM reste une hypothèse **jusqu'à preuve runtime**.

## P1 — Accès OWNER et détails TrueNAS sur smartphone

- [x] **CODED (#382) :** entrée `Owner access` en HTML, panneau léger
  `?operator=1`, revalidation `online/pageshow/visibilitychange`
  et séparation OWNER / read-only. Aucun secret stocké dans le navigateur.
- [ ] **Déploiement TrueNAS :** classifier l'ancien build Docker en
  lecture seule depuis `nabla-compose`, corriger sa cause, puis obtenir
  un build accepté 6/6 et un SHA d'image attesté. Préserver le runtime
  existant en cas d'échec.
- [ ] **Recette OWNER :** en HTTPS depuis le Wi-Fi approuvé, constater
  le bouton, se connecter via le formulaire, puis vérifier
  `authenticated=true`. Distinguer 401 (clé), 403 (source/origine)
  et 503 (configuration), sans élargir les CIDR ou faire confiance
  à un proxy non vérifié.
- [ ] **Détails :** vérifier `?operator=1&ui_full=1` sans gel, les
  cartes DNS/TCP/TLS/HTTP/token/Cloudflare, les détails TrueNAS,
  les liens upstream/downstream canonisés et le cache de fraîcheur.
- [ ] **UX mobile/a11y :** filtres horizontaux, focus clavier,
  navigation des drawers, panneaux rapides et états non bloquants ;
  ne jamais afficher une sonde inconnue comme verte.

**Done P1 :** OWNER accessible depuis la page publique sur source approuvée,
session authentifiée, cartes détaillées fonctionnelles, accès WAN non
autorisé toujours refusé.

## P1 — Fiabilité de la télémétrie, des sondes et du catalogue

- [ ] **Gatus :** réconcilier chaque service/sonde canonique avec
  `declared / observed / missing_monitor / no_sample / intentionally_unmonitored`,
  puis classer les 24 échecs historiques sans les supposer encore actifs.
- [ ] **Prometheus/exporters :** vérifier `METRICS_SCRAPE_KEY`,
  `up{job="fastapi_sample"} == 1`, Postgres/Redis et métriques
  d'exporters ; un `401` anonyme attendu n'est pas une panne.
- [ ] **Topologie et exposition :** confronter `catalogRevision`,
  unités de déploiement Garage S3/Admin/UI, liens upstream/downstream,
  Gatus et preuves outside-in ; distinguer source déclarée,
  sondage LAN, Access 302/403 et indisponibilité réelle.
- [ ] **pfSense/Cloudflare :** qualifier les refus, DNS, transport,
  API, tunnel et token depuis le bon point d'observation ;
  ne pas augmenter la charge des sondes sans mesure.
- [ ] **Preuves :** chaque carte doit conserver l'horodatage, l'âge,
  la provenance et l'état `DOWN / DENIED / UNVERIFIED / NOT_RUN`
  plutôt qu'un statut vert conjectural.

**Done :** couverture et santé justifiées par une mesure fraîche,
sans confusion entre API Cloud, LAN TrueNAS et collecteurs.

## P2 — Sécurité, maintenabilité et interopérabilité

- [ ] **RoutePolicy :** inventorier HTTP/ASGI/WebSocket/MCP/A2A,
  fermer les dérogations temporaires uniquement après tests négatifs
  des rôles PUBLIC/SERVICE/OWNER/INTERNAL et validation des consommateurs.
- [ ] **Trace et refactoring :** propager `traceparent` /
  `X-Nabla-Trace-ID` depuis Site Alban ; consolider
  `platform_metrics.py`, `health_routes.py` et les projections JS,
  avec tests de non-régression et limites de requêtes.
- [ ] **Sécurité/qualité :** prouver Betterleaks, Trivy, CodeQL et les
  autres gates requises sur le SHA exact ; traiter [issue #355](https://github.com/AlbanAndrieu/fastapi-sample/issues/355)
  seulement après deux runs master réellement verts, sans écraser
  les modifications humaines.
- [ ] **Intégrations privées :** qualifier LiteLLM, OpenRAG, Sentry,
  Pyroscope et imports DefectDojo avec identité limitée, budget,
  provenance et protections de secrets.
- [ ] **APISIX / DAST :** maintenir le POC API gateway et les scans
  profonds hors du chemin critique ; ne pas dupliquer la couverture
  de Site Alban ni déclencher des scans actifs sans périmètre autorisé.

Les hypothèses historiques détaillées demeurent dans le
[backlog à requalifier](engineering-backlog.md), pas dans l'ordre
d'exécution courant.

## Procédures et responsabilités

1. **Reprendre #382 :** [skill local-first](../.agents/skills/local-first-quality/SKILL.md),
    `just agent-context ui`, puis `just ui-quick`. Le skill FastAPI
    conserve L2 = `agent-quality-gate.sh --fix`, L3 =
    `agent-publish.sh`. Les outils Compose `agent-loop` et
    `agent-pre-push` ne sont pas les outils de ce dépôt.
2. **Diagnostiquer Cloud Loading :**
    [runbook UI](runbooks/fastapi-cloud-api-ui-freeze-20261026.md).
3. **Valider TrueNAS/OWNER/Gatus :**
    [recette consolidée](runbooks/fastapi-truenas-owner-acceptance-20261029.md).
4. **Rechercher un incident antérieur :**
    [registre](incidents.md) et archives, pas des statuts de production
    extrapolés depuis GitHub.

**Ownership :** FastAPI possède ses API, projections et diagnostics ;
[nabla-compose](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap.md)
possède TrueNAS, déploiement Docker, HAProxy/pfSense, Vaultwarden,
Gatus et Prometheus ; [Site Alban](https://github.com/AlbanAndrieu/nabla-site-alban)
possède la présentation Next.js, ses icônes et le cache SERVICE.
Pas de mutation de `master`, pas de CI GitHub avec crédits épuisés,
pas d'automerge, pas de bypass d'ACL ni d'intervention runtime implicite.

## P2 — Renovate et `helmfile.yaml` (29 octobre 2026)

- [x] `helmfile.yaml` (racine) déclare la release `fastapi-sample` sur le chart local `charts/generic-service`. Le gestionnaire natif `helmfile` de Renovate 44.2.1 l'extrait sans erreur (`--platform=local --dry-run=lookup`) : `skipReason: local-chart`, attendu.
- [ ] L'image suivie par `helm-values` et `kustomize` est encore `registry.gitlab.com/AlbanAndrieu/fastapi-sample` (`1.2.3`, `latest`), alors que l'image publiée est `ghcr.io/albanandrieu/fastapi-sample`. Preuve à fournir : aligner le dépôt d'image et la valeur du chart, puis un run Renovate qui propose une mise à jour réelle.
- [ ] Premier run planifié du workflow `Renovate` après fusion : vérifier dans le Dependency Dashboard la présence du fichier `helmfile.yaml`. `NOT_RUN`.

## P0 — master rouge : pytest complet (30 octobre 2026)

La gate exécute `pytest --maxfail=1` en ordre aléatoire : chaque run ne montrait qu'un échec. Sur `7fbd2f61`, la suite complète donnait **28 échecs**. Aucun n'était une régression fonctionnelle : les tests n'avaient pas suivi des changements volontaires (#370, #373, #376–#382) fusionnés en `[skip ci]`.

- [x] **TESTED (branche `build/helm/renovate-helmfile`) :** tests réalignés en gardant leur intention ; aucun contrôle d'accès affaibli, aucun seuil relevé. Clé `metrics_scrape_key` ajoutée aux réglages de test ; `api-health.js` ramené de 162 à 97 lignes par extraction de `api-health-visibility.js` ; `api.css` à 19 imports via `api-platform-services.css` ; test de worktree portable sous macOS ; `scripts/diagnose-production-api-ui-freeze.py` renommé `scripts/diagnose-api-ui-freeze.py` (`check()` découpé, complexité ≤ 10). `uv run pytest -q` : 1879 réussis, 0 échec ; `node --test tests/js/*.test.mjs` : 35/35 ; `agent-quality-gate.sh --fix` : PASS (L2).
- [ ] Le lanceur `scripts/diagnose-production-api-ui-freeze.mjs` porte encore `production` dans son nom ; à renommer si souhaité (runbook, `validate-fastapi-ui-acceptance.py` et tests JS à suivre).
- [ ] Retirer l'entrée `.quality-gate-large-deletions` du renommage après fusion.
- [ ] **UI riche :** l'extraction de `api-health-visibility.js` n'est vérifiée que par les tests ; vérifier `/api`, `?ui_safe=1`, `?ui_full=1` et `?operator=1` dans un navigateur réel. `NOT_RUN`. Formatage Biome JS/CSS `NOT_RUN` localement.
- [ ] **Clôture #355 :** `bash scripts/agent-publish.sh` sur un HEAD propre, puis deux runs `master` consécutifs verts. La CI hébergée n'a pas été lancée par l'agent.

## P2 — Claude Code et Codex sur la même workstation (30 octobre 2026)

- [x] **TESTED :** verrou de gate par worktree (`QG_LOCKED`, code 75 ; verrou orphelin repris par `QG_STALE_LOCK`) ; `QUALITY_PYTEST_MAXFAIL=0` liste tous les échecs pytest ; hook `shell-lint` local (shellcheck épinglé par mise), l'ancien hook distant plantait avec `DEBUG=true` exporté par Claude Code ; `AGENTS.md` neutre (Claude Code, Codex, OpenCode) avec une worktree par agent. Deux gates concurrentes dans un checkout : la seconde refusée (75), le verrou libéré ensuite.
- [ ] **Codex :** absent de cette session (`codex` hors `PATH`, pas de `~/.codex`). Preuve à fournir : depuis Codex, dans une worktree séparée, vérifier qu'il charge `AGENTS.md` et `.agents/skills/local-first-quality`, puis lancer `bash scripts/agent-quality-gate.sh --fix`. `NOT_RUN`.
- [ ] Les règles globales du propriétaire (`~/.claude/CLAUDE.md` et ses hooks de garde) ne s'appliquent qu'à Claude Code ; les reporter dans `~/.codex/AGENTS.md` si Codex doit les suivre hors de ce dépôt.

## P1 — Suites de l'analyse de sécurité (30 octobre 2026)

Constats revalidés sur `master` `2674d4a5`. Déjà corrigés sur `master` : `/admin`, `/mcp` et `/a2a` refusent par défaut (503 sans clé, `nabla/route_policy.py`) ; Trivy dépôt bloquant et `uv.lock` analysé ; `deploy.yml` supprimé.

- [x] **CODED :** `docker-compose.yml` (API + Postgres/Redis/Prometheus/Grafana de développement) supprimé ; le runtime homelab de référence est [`nabla-compose/apps/sample/compose.yml`](https://github.com/AlbanAndrieu/nabla-compose/blob/master/apps/sample/compose.yml). `docker-compose.yaml` (smoke de l'image seule) est conservé.
- [x] **Jeton GitLab** ignoré dans `.gitleaksignore` (`terraform/nomad/jobs/test/test-env-secret.nomad`, 4 commits absents de l'historique GitHub) : révocation confirmée par le propriétaire le 30/10. Les empreintes restent pour ne pas réalerter.
- [ ] **Inventaire FastAPI Cloud (noms seulement) :** `NOT_RUN` — conteneur agent sans identifiants et `api.fastapicloud.com` refusé par sa politique réseau. Preuve à fournir depuis la workstation : `mise exec -- uv run fastapi cloud env list | grep -oE '(ADMIN_ACCESS_KEY|DIAGNOSTICS_ACCESS_KEY|METRICS_SCRAPE_KEY|MCP_OPS_KEY|MCP_OPS_REQUIRE_KEY|MCP_CLIENTS|HOMELAB_PUBLIC_DIAGNOSTICS_READONLY|OPS_ROUTE_POLICY_STRICT)' | sort -u` (n'affiche aucune valeur).
- [ ] **Dérogation `HOMELAB_PUBLIC_DIAGNOSTICS_READONLY` (défaut `true`) :** la production sert `/api/homelab/status` en anonyme (run nabla-compose *Production Security* `41044286454`, 30/10 10:55 UTC, sans clé). La liste inclut `/api/health-board` (hôtes, ports, erreurs des sondes internes) et `/api/runtime/topology` (IP d'egress). À fermer avec l'item RoutePolicy (P2), ou à remplacer par une projection publique assainie.
- [ ] **`/v1/mcp/ops/*`, `POST /run`, notes :** politique `REVIEW`, et `OPS_ROUTE_POLICY_STRICT=false` par défaut ⇒ anonymes. `MCP_OPS_REQUIRE_KEY=false` par défaut ⇒ MCP Ops ouvert sans `MCP_OPS_KEY`. Preuve : test négatif 401/503 anonyme pour chacun.
- [ ] **Outillage agent :** `.claude/settings.local.json` versionné avec `Bash(direnv exec *)` (exécution arbitraire sans confirmation) ; à retirer de Git. Images MCP non épinglées (`.mcp.json`, `opencode.json`, `.cursor/mcp.json`) alors qu'elles reçoivent des jetons.
- [ ] **CI/Supply chain :** supprimer ou durcir `tmp-agent-autofix.yml` (`push` sans filtre de branche, `contents: write`) ; activer `vulnerabilityAlerts`/`osvVulnerabilityAlerts` dans `renovate.json`.
- [ ] **Héritage :** `job.nomad` (Redis sans `requirepass`, TCP Traefik sans TLS) n'est référencé par aucun script ; le supprimer si Nomad n'est plus un runtime.
- [ ] **En-têtes HTTP :** `nosniff`, protection de cadre et HSTS absents en production (baseline `config/security/production-http-baseline.json` de nabla-compose).
