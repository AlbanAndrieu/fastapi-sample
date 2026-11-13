# Roadmap active — FastAPI Sample

> **Réconciliation du 13 novembre 2026.** Ce document suit exclusivement les travaux FastAPI **non acceptés**. Vue de décision transversale : [portefeuille Homelab](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap-portfolio.md). Configuration TrueNAS, CSI, pfSense, Cloudflare Tunnel et secrets : [roadmap nabla-compose](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap.md).

Une PR fusionnée n'est pas une acceptation runtime. Utiliser `CODED` (code fusionné), `TESTED` (tests exécutés sur SHA exact), `DEPLOYED` (image/SHA déployé identifié), `ACCEPTED` (comportement constaté sur cette image), `NOT_RUN` et `NOT_VERIFIED` (absence de preuve). Les refus Cloudflare `DENIED` et les diagnostics non exécutés ne sont pas `DOWN`.

## P0 — Recette de production, sécurité et budget

| ID | État code au 13/11 | À faire et critère de clôture |
| --- | --- | --- |
| **F01 — Cloud UI et OWNER** | **CODED** (#382, #383, #390), recette récente **NOT_VERIFIED** | Attester `/v2/version` sur Cloud et TrueNAS, tester dans Chromium `/api`, `ui_safe=1`, `ui_full=1`, `operator=1` et combinaison OWNER ; absence de gel JS, défilement du panneau TrueNAS, aucun détail privé anonyme. [Recette](runbooks/fastapi-truenas-owner-acceptance-20261029.md). |
| **F02 — FinOps FastAPI Cloud Nano** | **CODED** : PR [#419](https://github.com/AlbanAndrieu/fastapi-sample/pull/419) fusionnée le 11/11 ; **NOT_VERIFIED** en production | Mesurer le **CPU vCPU**, la RAM, les réplicas et latences dans FastAPI Cloud Metrics avant/après à trafic comparable. Vérifier polling OWNER 180 s, absence de polling public, profilage Cloud inactif par défaut, cgroup v2 à la demande. Ne pas confondre CPU processus, cAdvisor TrueNAS et métriques de facturation. [Budget runtime](runbooks/fastapi-cloud-runtime-cost-guard.md). |
| **F03 — Couverture des sondes** | Calculs et classifications **CODED**, preuve fraîche **NOT_VERIFIED** | Rapprocher `entityRef`/`catalogRevision`, Gatus, Prometheus et observation directe ; exposer `UP`, `DOWN`, `NO_SAMPLE`, `NOT_MONITORED`, `DENIED`, `STALE` sans faux vert. Les 67,9 % evidence / 7,1 % healthy du 05/11 restent une **ancienne mesure**, non une situation actuelle. [Couverture](runbooks/cloud-probe-evidence-coverage.md) et [acceptation](runbooks/fastapi-observability-acceptance.md). |
| **F04 — Qualité et publication locale** | Corrections CI et gates **CODED** ; HEAD actuel **NOT_VERIFIED** | `just ui-quick` puis L2 (`scripts/agent-quality-gate.sh --fix`) et L3 (`scripts/agent-publish.sh`) au SHA exact ; vérifier les suites et obtenir **deux runs master** consécutifs réels avant de clôturer [issues/355](https://github.com/AlbanAndrieu/fastapi-sample/issues/355). Aucun FAIL/timeout converti en PASS. [Qualité](../.agents/skills/local-first-quality/SKILL.md). |
| **F05 — Identité publique et accès** | Cible `fastapi-sample.albandrieu.com` **CODED** ; DNS final **NOT_VERIFIED** | `nabla-compose` possède l'apply OpenTofu, la route Tunnel et Access. FastAPI vérifie séparément santé LAN, réponse 302/403 Access, CDN/WAF, Cloud et DNS `dns_sample` ; ne pas exempter le WAF pour faire passer une sonde. [Contrat réseau](fastapi-sample-cloudflare-network-contract.md). |

**Done P0** : SHA effectivement servi, OWNER et anonymous recettés sur navigateur, budget observé et sondes expliquées avec leur fraîcheur. Aucun droit supplémentaire implicite.

## P1 — Qualité de l'observabilité et expérience opérateur

| ID | État | Preuve et prochaine action |
| --- | --- | --- |
| **F06 — Accueil Operations Overview** | Démonstration météo remplacée dans [#396](https://github.com/AlbanAndrieu/fastapi-sample/pull/396), **CODED** ; runtime **NOT_VERIFIED** | Confirmer rendu sans clic, caches publics sans information OWNER, froid/chaud et mode déconnecté ; la démo est uniquement sur `/demo/sensors`. [Transition](runbooks/home-operations-transition.md). |
| **F07 — Heatmap et ressources** | Tri cAdvisor CPU/RAM/FS/RX+TX [#418](https://github.com/AlbanAndrieu/fastapi-sample/pull/418) fusionné ; **CODED**, recette OWNER **NOT_RUN** | Test Node, session OWNER mobile et anonyme, `0` mesuré distinct de l'absence `—`, échelle max sur les lignes visibles ; compléter occupation **ZFS dataset** sans l'inférer de `container_fs_usage_bytes`, NetFlow/Sankey seulement avec flux sourcés. [Transition](runbooks/home-operations-transition.md). |
| **F08 — Runtime TrueNAS et démarrage** | PostgreSQL `fastapisample` TLS 1.3/`verify-full` et réception Sentry documentés le 13/11 côté Compose ; démarrage lent encore ouvert | Isoler trois pauses d'environ 1 min avant Unleash, Logfire et Sentry ; instrumenter par phase avec borne de durée, vérifier `/health`, `/readyz`, les sondes Prometheus et le chemin LiteLLM/OpenRAG sans régression. **Déploiement et APP ID appartiennent à Compose**. [Runbook](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/runbooks/fastapi-sample-truenas-diagnostics.md). |
| **F09 — Projections et intégrations** | Vue couches réseau/Cloudflare/Prometheus **CODED** ; **NOT_VERIFIED** au runtime | Valider cache L1/L2 Redis opt-in sans mélange d'environnements, critères `unknown/warn` et âge des preuves ; authentification scrape, pas de sonde WAN pfSense interdite. [Connexions](runbooks/truenas-cloud-connection-probes.md). |
| **F10 — Scans et DefectDojo** | Endpoints et export privés préparés, import **NOT_VERIFIED** | Product/engagement et RBAC limités, import LAN sans secret, suivi asynchrone jusqu'à `Processed`, déduplication et refus inter-produit ; coordination avec les ressources Compose, sans importer des secrets en CI. [Import privé](runbooks/defectdojo-fastapi-private-import.md). |

**Done P1** : couverture sans fausses classifications, interface mobile utilisable, sondes et métriques attribuées à leur source, aucun secret émis dans le navigateur.

## P2 — Architecture, sécurité et dette technique

- **RoutePolicy/ASGI/JWT** : HTTP, WebSocket, MCP/A2A et consommateurs PUBLIC/SERVICE/OWNER/INTERNAL ; éprouver JWKS/JWT, mauvais issuer/audience, perte JWKS et route denial avant `OPS_ROUTE_POLICY_STRICT`. **Non activé par simple refactoring.**
- **OIDC Keycloak** : identité FastAPI distincte de PostgreSQL OAuth, gestion MFA et révocation ; architecture et exposition Keycloak appartiennent à Compose.
- **Fédération TrueNAS → Cloud** : agrégats signés, datés, minimisés et authentifiés ; aucun accès LAN depuis Cloud, aucune IP privée ni secret dans un DTO public.
- **Qualité des scripts** : `scripts/ci/quality-git.sh` pour la base Git, `quality-lock.sh` pour `flock -o`, `quality-timeout.sh` pour les échéances, `run-pytest-bounded.sh` pour la CI. Conserver le rapport lisible `run-pytest-compact.sh` pour les sessions locales. **Ne pas refusionner ces CLI dont les contrats de sortie diffèrent**. Retirer les hooks dupliqués prek/ruff/gitlint uniquement après tests ciblés.
- **Maintenance** : Renovate et Helm sans automerge, qualité Python et Node, revue des tests et règles sécurité de PR. Les chantiers anciens non requalifiés restent dans [engineering-backlog.md](engineering-backlog.md), jamais automatiquement P0.

## Travaux terminés et documents de preuve

Les livraisons **CODED** déjà fusionnées (#382, #383, #390, #396, #418, #419) ne doivent plus être planifiées comme implémentations à refaire : seules leurs **recettes sans preuve** restent dans F01–F09. Les mesures et dysfonctionnements d'octobre ne sont pas l'état courant.

Historique : [archive avant consolidation](archive/2026-10-29/engineering-roadmap-before-consolidation.md), [registre d'incidents](incidents.md), [journal de réconciliation du 13/11](archive/2026-11-13-roadmap-reconciliation.md), [guide documentation](README.md).

- [ ] **Qualité locale / prépublication :** [PR #392](https://github.com/AlbanAndrieu/fastapi-sample/pull/392)
  centralise l'exécution pytest bornée. Le même lot regroupe la résolution
  Git `QUALITY_BASE_REF` des trois scripts de contrôle afin que le comportement
  soit cohérent entre worktrees, HEAD détaché et pre-push. Tests Git isolés
  écrits ; smoke Bash local exécuté. **L2/L3 sur SHA final NOT_RUN**.



- [ ] **RoutePolicy/ASGI :** couvrir HTTP, WebSocket, MCP/A2A,
  PUBLIC/SERVICE/OWNER/INTERNAL ; valider JWKS/JWT, consommateurs et
  clients externes avant `OPS_ROUTE_POLICY_STRICT` ou changement Access.
- [ ] **Observabilité transverse :** `traceparent` /
  `X-Nabla-Trace-ID` entre Site Alban et FastAPI ; réduire les
  duplications `platform_metrics.py`, `health_routes.py` et modules JS
  avec tests de non-régression. **01/11 CODED :** `utc_now`/`short_error`
  uniques (`platform_health_diagnostics`, 6 copies retirées), warm-up des
  sondes extrait dans `probe_runtime.py`, C901 de `health_routes.py`
  corrigé (509 → 449 lignes). Restent : `health_routes.py` > 400 lignes,
  `_short_error` volontairement réduit au nom de classe dans
  `cloudflare_*`, modules JS ; preuve : L2/L3 sur le HEAD de la PR.
- [ ] **Renovate / Helm :** aligner les références d'image
  `registry.gitlab.com` et `ghcr.io`, vérifier l'extraction
  `helmfile.yaml` dans un vrai Dependency Dashboard ; conserver
  `automerge=false`.
- [ ] **Scans / intégrations :** vérifier Betterleaks/Trivy/CodeQL,
  DefectDojo à permissions limitées, Sentry/Pyroscope, chaîne
  LiteLLM/OpenRAG ; APISIX et DAST approfondi restent différés,
  sans scans actifs hors périmètre autorisé.
- [ ] **Agents/outillage :** vérifier Codex en worktree dédié avec
  `AGENTS.md` et le skill `local-first-quality` ; ne pas supposer
  une installation existante. Nettoyer l'exception
  `.quality-gate-large-deletions` quand le renommage prévu est fusionné.
  Renommer le script JS `diagnose-production-api-ui-freeze.mjs`
  uniquement si cela simplifie réellement la maintenance.
  **01/11 CODED :** `scripts/` passe à 0 écart ruff (12 → 0 : 7 C901
  découpés, S101, S310 justifiés sur origines figées) et 8 scripts
  reformatés ; test ajouté pour `github-actions-usage.py`. La base Git
  des gates est unifiée dans `scripts/ci/quality-git.sh` (#392), dont
  les trois contrats de pin/runner rouges sur master sont corrigés.
  Reste `diagnose-local-runtime-dependencies.py` (634 lignes) ;
  preuve : L2/L3 sur le HEAD de #392.

- [ ] **Verrous et durées locales (01/11) :** la branche
  `refactor/quality-lock-timeouts-20261101` utilise `flock` pour
  protéger chaque worktree sans PID réutilisable, et impose des délais
  aux contrôles locaux, tests et publication. Un timeout reste un échec.
  Le superviseur `flock -o` empêche les subprocessus orphelins de
  conserver le verrou après SIGKILL. Tests de régression ajoutés.
  Migration explicite des anciens verrous, sans effacement automatique.
  **CODED ; L2/L3 au SHA final à valider.**

- [ ] **Couverture des sondes Cloud (03/11, CODED) :** PR
  `fix/cloud-probe-evidence-coverage-20261103` : estimation sur tous les
  candidats, liste des emplacements sans preuve, catégories distinctes
  Cloudflare Access/auth/DNS/TLS/timeouts, horodatage et diagnostic UI.
  Le moteur reste **déclenché par les requêtes**, cache par worker :
  `100 %` n'est pas garanti par une seule durée de rotation.
  Voir [runbook Cloud](runbooks/cloud-probe-evidence-coverage.md).
  **Reste :** validation locale L1/L2/L3 au HEAD exact, diagnostic des
  16 warnings sur données réelles, activation/validation du Redis partagé
  public (opt-in, jamais LAN), puis recette du déploiement (SHA et mesures).
- [ ] **Hooks Git avec prek (05/11, CODED) :** branche
  `feat/prek-parallel-hooks`. prek 0.5.10 remplace pre-commit (même
  `.pre-commit-config.yaml`) dans `mise run hooks`, les gates, le
  `justfile`, tox et la CI. Les contrôles en lecture seule partagent
  `priority: 100` (parallèles après les correcteurs séquentiels). Ajout de
  `groups` (`security`, `workflow`, `slow`) et `hide_status`.
  **Preuve L3 (06/11) :** `agent-publish.sh` PASS sur le Mac avec
  `brew install util-linux` (`flock` ajouté au PATH, keg-only).
  **NOT_RUN :** CI preflight Linux à cache prek froid.
  **Reste :** (1) `.envrc` installe encore pre-commit (fichier du
  propriétaire) ; (2) doublon `ruff`/`ruff-check` (exclusion
  `nabla/__init__.py` à arbitrer) ; (3) doublon commitizen/gitlint sur
  `commit-msg` ; (4) `commitizen-branch` est en `pre-push` dans la config
  principale, que `mise run hooks` n'installe pas pour ce stage : il ne
  s'exécute jamais ; (5) `uv-sync` en `post-checkout`/`post-merge`
  ; (6) réévaluer hk quand `hk migrate pre-commit` convertit la majorité
  des hooks (05/11 : 27 convertis, 44 restent sur prek).
- [ ] **Fédération TrueNAS → Cloud :** concevoir un transport d'agrégats
  signés, horodatés et autorisés. Aucun accès LAN direct depuis Cloud,
  aucune publication d'IP privée ni état vert sans preuve d'origine.

- [ ] **P1 — Connexions TrueNAS ↔ Cloud, Prometheus et Cloudflare (04/11, CODED) :**
  projection des couches distinctes dans le health-board et le dashboard.
  Depuis `FASTAPI_RUNTIME_MODE=homelab` uniquement, vérification HTTPS de
  `fastapi-sample.fastapicloud.dev/api/ui/session` et résolution publique A
  via Cloudflare DoH (récursif, **pas** l'API DNS de la zone). Appels fixes,
  simultanés, bornés et mis en cache 90 s. Prometheus : distinguer redirection
  Access, 401/403, 429, timeout, connexion et réponse invalide, sans transformer
  un scrape UP en disponibilité applicative.
  **Restent :** tests ciblés et L2/L3 sur SHA final, recette runtime TrueNAS,
  confirmation des métriques et des voies d'accès, validation DNS/Tunnel.
  La [PR #396](https://github.com/AlbanAndrieu/fastapi-sample/pull/396)
  présente aussi les catégories de diagnostic dans les cartes.
  Voir [runbook de connexion](runbooks/truenas-cloud-connection-probes.md).

- [x] **P1 — Remplacer la démonstration météo de `/` (04/11, CODED, PR #396 fusionnée) :**
  page `Operations Overview` sans base PostgreSQL ; sondes et sécurité
  depuis le health-board ; CPU/mémoire/débit cAdvisor depuis la topologie ;
  latence HTTP mesurée sans prétention de RTT ; courbes de l'onglet uniquement.
  `/demo/sensors` conserve les anciens diagrammes en démo explicite ;
  génération synthétique retirée du startup. Accès propriétaire requis
  pour les informations détaillées, anonymes limités au répertoire public.
  **Extension 08/11 — PR complémentaire :** `query_range` propriétaire,
  fenêtres 1 h/24 h/7 j, CPU/mémoire/débit, p95 HTTP, Gatus facultatif,
  corrélation sur paires réelles et aucun faux zéro cAdvisor.
  **Reste :** Node/pytest L2/L3 sur checkout complet, recette mobile et
  confirmation des séries sur TrueNAS/Cloud ; aucun déploiement implicite.
  Voir [runbook](runbooks/home-operations-transition.md).
  **Extension 08/11 — pulse TrueNAS en direct (CODED) :** sur Cloud les
  sections capacité restaient vides (Prometheus LAN seulement). Nouveau
  `GET /api/home/appliance/pulse` (OWNER) : `system.info`, `alert.list`,
  `pool.query`, `interface.query`, `app.query`, `reporting.netdata_graphs`
  et `reporting.netdata_get_data` (1 h) en une session, cache 30 s ;
  section « Appliance TrueNAS en direct » et liste d'interdépendances du
  même instantané (stockage ↔ alertes, mémoire ↔ Apps CRASHED, charge,
  liens physiques). **Preuves suivantes :** `state=observed` depuis une
  session OWNER sur Cloud et TrueNAS ; si `partial`, ajouter les rôles
  `REPORTING_READ`/`ALERT_LIST_READ` à la clé d'observation ; confirmer les
  légendes netdata réelles (`idle`, `used`/`free`, `received`/`sent`) ou
  adapter la conversion ; recette mobile de la nouvelle section.

- [ ] **P0 — Bascule `sample.albandrieu.com` → `fastapi-sample.albandrieu.com` (10/11, CODED) :**
  les sondes DNS (`dns_sample`) visent désormais le nouveau nom ; `compose.yml`
  le déclarait déjà. Constat du 10/11 : aucun enregistrement DNS pour le
  nouveau nom (le `tofu apply` du renommage, nabla-compose
  `terraform/cloudflare`, n'a jamais été exécuté) alors que l'ancien nom
  répond derrière Cloudflare Access. Jusqu'à l'apply, `dns_sample` reste en
  `fail`/`nxdomain` : c'est l'état réel. **Preuve suivante :** apply
  Cloudflare depuis la workstation, puis `dns_sample=ok` et défi Access (302)
  sur `https://fastapi-sample.albandrieu.com/` ; ensuite retrait de l'ancien
  nom des destinations Access.

## Documentation et séquence de reprise

1. [Guide local-first](../.agents/skills/local-first-quality/SKILL.md) :
    `just agent-context ui` → `just ui-quick` → L2 → L3 ;
    utiliser le skill FastAPI, **pas** les recettes `mise agent-loop`
    propres à Compose.
2. [Gel UI Cloud](runbooks/fastapi-cloud-api-ui-freeze-20261026.md) :
    classifier navigateur, API et authentification.
3. [Recette Cloud/TrueNAS/OWNER](runbooks/fastapi-truenas-owner-acceptance-20261029.md) :
    checkout isolé, contrôle sans secrets et GO manuel.
4. [Incidents](incidents.md) : preuves datées ; [backlog](engineering-backlog.md) :
    anciens travaux à requalifier, sans les promouvoir automatiquement en P0.
5. [Roadmap avant consolidation](archive/2026-10-29/engineering-roadmap-before-consolidation.md) :
    historique en lecture seule.

**Responsabilités :** FastAPI = API, interface, sonde et DTO ;
[nabla-compose](https://github.com/AlbanAndrieu/nabla-compose) = déploiement
TrueNAS, secrets, Gatus, Prometheus, firewall et ingress ;
[Site Alban](https://github.com/AlbanAndrieu/nabla-site-alban) = composants
Next.js et leur cache navigateur. Aucun changement d'ACL, secret, CI,
merge ou déploiement implicite.

- [ ] **P1 — Accueil Cloud sans clic (09/11, PR de suivi, CODED) :**
  relances `pending/stale` 2/4/8/15/30 s, rendu de l'inventaire public
  dès la première réponse, `sessionStorage` de noms sans statuts,
  cache Redis L2 facultatif et isolé par environnement. L0 n'enregistre
  aucun résultat de sonde ni donnée OWNER. **Reste :** Node/pytest
  en checkout complet, test cold-start Cloud et contrôle TrueNAS.
  Voir [migration de l'accueil](runbooks/home-operations-transition.md).

- [ ] **P0 — FastAPI Cloud runtime FinOps / 10 novembre 2026 (CODED)** :
  optimisation de la fréquence des reconstructions health-board sur Cloud
  (cache 180 s, tentatives espacées 30 s, backoff échec 90 s),
  échantillonnage psutil 30 s contre 5 s, polling public Cloud 60 s
  contre 30 s, sans toucher à la cadence TrueNAS.
  Le statut public des sondes tient compte de la durée réelle de validité
  des preuves lors de la réutilisation d'un snapshot.
  Objectif théorique : ~6 fois moins de vagues Cloud en régime de cache,
  **sans prétendre mesurer le CPU réel**. Les preuves réelles nécessitent
  l'écran FastAPI Cloud → Metrics (CPU en vCPU, RAM, réplicas), et la
  recette après déploiement. Voir
  [runbook de budget Cloud](runbooks/fastapi-cloud-runtime-budget.md).

- [ ] **P0 — FastAPI Cloud : budget runtime (09/11, CODED / non déployé)** :
  accueil public sans fan-out, réconciliation OWNER TTL/backoff 180 s,
  arrêt des trois boucles résidentes en Cloud, pollings navigateur
  publics arrêtés et OWNER réduits, échantillon CPU-time/RSS
  sur demande seulement. Aucun réglage automatique de CPU/replicas.
  Validation requise : Node 22, pytest, smoke test de version,
  comparaison Metrics FastAPI Cloud avant/après. Ne pas modifier
  l'autorisation du LAN. Voir
  [runbook](runbooks/fastapi-cloud-runtime-cost-guard.md).

## P1 — Visualisation des ressources et flux Homelab (10 novembre 2026)

- **CODED dans la PR #405, pas déployé :** carte thermique OWNER-only sur l'accueil `/`, calculée à partir du snapshot cAdvisor déjà autorisé et mis en cache. Jusqu'à 12 services × 4 dimensions : cœurs CPU, RAM active, système de fichiers conteneur et débit RX+TX. Intensités normalisées **par colonne sur le maximum observé**, jamais sur la capacité. Mesure nulle `0` et mesure absente `—` restent distinctes.
- **Prochain jalon P0 :** après les tests locaux Node, Python et le quality gate, identifier le SHA actif avec `/v2/version` puis vérifier dans un navigateur OWNER la matrice, les classements, la mosaïque des sondes et l'absence de donnée privée dans une session anonyme.
- **Stockage P1 :** compléter cAdvisor par des métriques **ZFS dataset**, `used`/`available`/`quota`, issues de TrueNAS ou d'un exporter dédié ; ne jamais présenter `container_fs_usage_bytes` comme l'occupation de `cpool`.
- **Flux réseau P1 :** utiliser les séries RX/TX des conteneurs (cAdvisor) et les dimensions IPFIX/NetFlow d'Akvorado pour une vue Sankey *uniquement si source, destination, protocole et échantillonnage sont vérifiés*. Le débit global pfSense ne peut pas être attribué à une dépendance de catalogue.
- **Coût Cloud P0 :** aucune requête supplémentaire ajoutée à l'accueil ; le public Cloud utilise le snapshot autorisé sans réveil périodique. La métrologie CPU/réplicas se mesure sur FastAPI Cloud, pas à partir des CPU cAdvisor TrueNAS.

**11/11 — CODED, recette non exécutée :** enrichissement de la heatmap OWNER-only
avec tri local CPU/RAM/FS/réseau, sans nouvel endpoint ni requête réseau.
Le maximum de chaque colonne est calculé sur les 12 lignes **affichées** ;
les mesures absentes restent distinctes des zéros mesurés. Tests Node
de sélection / normalisation ajoutés. **Preuves restantes :** `node --test tests/js/home-operations-model.test.mjs`,
`just ui-quick`, gate L2/L3 sur
le SHA final, puis recette navigateur OWNER (petit écran, changement de tri,
session anonyme, télémétrie indisponible) et confirmation de la source
cAdvisor sur TrueNAS. Aucun déploiement revendiqué.

Références : [cAdvisor](https://github.com/google/cadvisor/blob/master/docs/storage/prometheus.md), [Grafana Node Graph](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/visualizations/node-graph/), [Akvorado](https://github.com/akvorado/akvorado), [Apache ECharts](https://echarts.apache.org/en/feature.html).

- [ ] **P0 — Budget Nano FastAPI Cloud, 11 novembre 2026 (CODED) :**
  réparer l'incohérence du polling OWNER (60 s effectifs contre 180 s
  prévus), et désactiver par défaut Pyroscope/Datadog sur Cloud
  (`FASTAPI_CLOUD_PROFILING_ENABLED=true` pour les réactiver).
  TrueNAS et contrôles OWNER inchangés. Tests de contrats ajoutés.
  **Reste** : validation pytest/Node sur le checkout, recette Cloud
  CPU/mémoire/réplicas par le panneau privé, confirmation du déploiement.
  Runbook : [FastAPI Cloud](runbooks/fastapi-cloud-runtime-cost-guard.md).

  **Mesures supplémentaires CODED :** lecture cgroup v2 sur action OWNER
  uniquement (`memory.current`, `memory.max`, quota CPU, OOM),
  affichage de la limite cgroup observée en priorité sur la référence
  Nano, sans promettre une consommation mensuelle connue. Tests Python
  de formats illimités/invalides et de lecture plafonnée à 4 Kio ;
  tests JS de la nouvelle présentation. Le maximum de réplicas Hobby
  est à vérifier manuellement, sans changement automatique.

## P0 — Catalogue Backstage v2 seul (P2.1.d, 13 novembre 2026)

- [ ] **CODED, non déployé :** `/sickz`, le tableau de santé, les politiques
  Cloudflare et `/api/homelab-services` lisent uniquement les routes
  `x-nabla.exposure` de `entities.json` (`nabla/api/catalog_routes.py`) ;
  `homelab-services.json`, `homelab-exposure-overrides.json`,
  `HomelabService` et les variables `HOMELAB_SERVICES_CATALOG_URL` /
  `HOMELAB_EXPOSURE_OVERRIDES_URL` sont supprimés. Le démarrage à froid
  utilise `nabla/api/data/catalog-snapshot.json`, copie octet par octet
  régénérée par `scripts/refresh-catalog-snapshot.sh`.
  **Ordre de fusion :** après nabla-compose #365, avant la suppression des
  fichiers legacy dans nabla-compose et avant la PR Site Alban v2.
  **Preuves restantes :** après déploiement, `/api/homelab-services`,
  `/api/site/catalog/v2`, `/api/site/health/v2` et `/api/homelab/status`
  répondent sur le même `catalogRevision` que nabla-compose `master`, et
  `/sickz` garde les mêmes verdicts de politique (TrueNAS direct :7000,
  Garage S3/Admin privés, pfSense refusé depuis Cloud).
- [ ] **Après la PR Site Alban v2 :** supprimer `/api/homelab-services`.
- [ ] **P2.1.f :** re-sourcer `service-topology.json` et `services.json`
  (`homelab_topology.py`, `homelab_declared.py`) depuis les relations
  Backstage, puis indexer les lignes du tableau de santé et
  `/api/site/health/v2` sur l'entity ref complète (aujourd'hui `id` =
  nom Backstage, suffixé du nom de route au-delà de la première).
