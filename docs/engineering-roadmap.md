# Roadmap active — FastAPI Sample

> **Réconciliation mise à jour le 14 novembre 2026.** Ce document suit exclusivement les travaux FastAPI **non acceptés**. Vue de décision transversale : [portefeuille Homelab](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap-portfolio.md). Configuration TrueNAS, CSI, pfSense, Cloudflare Tunnel et secrets : [roadmap nabla-compose](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap.md).

Une PR fusionnée n'est pas une acceptation runtime. Utiliser `CODED` (code fusionné), `TESTED` (tests exécutés sur SHA exact), `DEPLOYED` (image/SHA déployé identifié), `ACCEPTED` (comportement constaté sur cette image), `NOT_RUN` et `NOT_VERIFIED` (absence de preuve). Les refus Cloudflare `DENIED` et les diagnostics non exécutés ne sont pas `DOWN`.

## Rattachement au portefeuille Homelab unique

L'ordre **actif du portefeuille** est **H02/G1 → H01 → H05** : H02 (restauration PostgreSQL) puis H01 (CSI Talos) appartiennent à Compose ; FastAPI ne prétend pas valider ces opérations. La priorité révisée du 13/11 remplace l'ancien ordre H01 → H02 → H05. Le portefeuille [H01–H19](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap-portfolio.md) est l'unique arbitrage entre dépôts.

| Homelab | Actions FastAPI à réceptionner | Propriétaire de la mutation |
| --- | --- | --- |
| **H05** | **F03** (couverture + fraîcheur), **F09** (connexion Cloud/TrueNAS) ; preuves Gatus/Prometheus | Compose pour les exporters et cibles, FastAPI pour la projection |
| **H06** | **F01** (UI/OWNER), **F02** (FinOps Cloud Nano) | FastAPI, sans réveil ou exposition supplémentaire |
| **H04** | **F05** (DNS/Access), preuves négatives | Compose pour DNS/Tunnel/Access |
| **H14** | **F06–F07** (Operations Overview, heatmap OWNER) | FastAPI et sources mesurées côté Compose |
| **H17** | **F11** (catalogue V2 et suppression ordonnée des vues legacy) | Compose → FastAPI → Site Alban |
| **H19** | Aucune bascule Home Assistant dans FastAPI | Compose |

Les anciens identifiants **E01–E14** de #423 sont conservés comme [table de correspondance en archive](archive/2026-11-13-roadmap-reconciliation.md), pas comme seconde roadmap active. Aucun passage de `CODED` à `ACCEPTED` sans preuve runtime datée.

## Ordre d'exécution FastAPI — décision du 14 novembre 2026

L'arbitrage **spécifique à fastapi-sample** est **H05/F03+F09 → H17/F11**. Il s'applique aux développements et recettes applicatifs sans attendre H02/G1 ou H01. Le portefeuille infrastructure conserve séparément l'ordre H02/G1 → H01 → H05.

| Rang FastAPI | Travaux existants | Preuve de fin attendue |
| --- | --- | --- |
| **P0.1 — H05** | **F03 + F09** : couverture, fraîcheur et rapprochement Cloud/TrueNAS/Gatus/Prometheus | États sourcés par service et `entityRef`, âges d'observation contrôlés, `NO_SAMPLE`/`STALE`/`DENIED`/`NOT_RUN` distincts de `DOWN`, cache Redis L1/L2 isolé, preuves datées sur Cloud et TrueNAS |
| **P0.2 — H17** | **F11** : réception Backstage V2, affichage des services, dépendances et migration des consommateurs | `catalogRevision` cohérent sur les endpoints V2 et les consommateurs, aucune donnée OWNER en public, liens aval/amont sûrs, recette Site Alban avant suppression legacy |

Les autres items F restent ouverts dans leurs sections et seront réordonnés après réception de H05 puis H17 ; ceci ne crée pas un second backlog ni une condition de blocage infrastructure.

## Dette de code mesurée — analyse du 14 novembre (pas de nouveau backlog)

[Baseline inter-dépôts, méthodes et principaux fichiers](https://github.com/AlbanAndrieu/nabla-compose/pull/385)
dans `nabla-compose` : 703 fichiers de programmation, **3 938 960 octets** dans
FastAPI Sample à l'instantané GitHub `34a97b923d33ef0c4871c1800b221b58a216d700`
(dont `tests/` : 1,56 Mo et `nabla/api/` : 1,63 Mo). Les tailles des blobs
ne sont **pas** des lignes de code ni une évaluation de complexité.

| Priorité existante | Fichiers volumineux inspectés | Découpage envisagé et preuve |
| --- | --- | --- |
| **P0.1 H05 / F03 + F09** | `nabla/api/assets/api-probe-fanout-dashboard.js` (935 lignes), `api-service-operator-diagnostics.js` (942), `nabla/api/health_board.py` (608) | Isoler collecteurs, cache/fraîcheur, modèle d'état puis rendu, **sans changer** les codes `DENIED`/`STALE`/`NOT_RUN` ni introduire de requêtes Cloud supplémentaires ; tests de provenance TrueNAS → Cloud sur le SHA déployé |
| **P0.2 H17 / F11** | `nabla/api/assets/api-service-detail-drawer.js` (1 088 lignes) | Séparer contrat V2 `entityRef`/`catalogRevision`, mapping des preuves et gestion DOM ; tester contexte OWNER/anonymous, accessibilité mobile et absence de fuite avant retrait legacy |
| **P1 F06 + F07** | `nabla/api/assets/home-operations.js` (1 275 lignes), `home-operations-model.js` (856) | Garder le modèle pur et sortir cadence/transport du rendu ; contrôler coût CPU, single-flight, invalidation et DOM sans clignotement |
| **P1 F08** | `nabla/integrations/truenas_client.py` (576 lignes) | Compartimenter transport WebSocket, retries et conversion DTO ; vérifier les erreurs d'authentification, timeouts et phases de démarrage |
| **Contrats** | 303 fichiers de tests, 1,56 Mo (39,7 % du code suivi) | Mutualiser les fixtures répétées **après** analyse de couverture ; ne pas affaiblir les tests négatifs, SAST/SCA ou quality gates pour diminuer le volume |

Ce découpage est **un diagnostic d'emplacements candidats**, pas une
régression démontrée par la taille. Exécuter les corrections strictement
nécessaires aux preuves **F03/F09**, puis à **F11**, avant toute campagne
de refactoring esthétique. Les gros fichiers générés, notamment
`nabla/_version.py`, ne sont pas à éditer manuellement.

Sur la workstation possédant les deux checkouts, la métrique en
**lignes physiques** peut être recalculée via l'outil offline de la
[PR Compose #385](https://github.com/AlbanAndrieu/nabla-compose/pull/385) :

```bash
cd ../nabla-compose
python3 scripts/quality/code-hotspots.py --root ../fastapi-sample --limit 20
```

Ce contrôle Git local ne contacte ni TrueNAS ni FastAPI Cloud et ne
prouve pas l'état d'un service. Une mesure de maintenance H11 reste
distincte de l'acceptation applicative F03/F09/F11.

## P0 — Priorités applicatives H05 → H17 et contrôles transversaux

| ID | État / réception au 14/11 | À faire et critère de clôture |
| --- | --- | --- |
| **F03 — Couverture des sondes** | Calculs et classifications **CODED**, preuve fraîche **NOT_VERIFIED** | Rapprocher `entityRef`/`catalogRevision`, Gatus, Prometheus et observation directe ; exposer `UP`, `DOWN`, `NO_SAMPLE`, `NOT_MONITORED`, `DENIED`, `STALE` sans faux vert. **SWR UI public fusionné dans [#436](https://github.com/AlbanAndrieu/fastapi-sample/pull/436) et [#439](https://github.com/AlbanAndrieu/fastapi-sample/pull/439)** : dernier résumé public daté conservé jusqu'à **7 jours** (historique, jamais verdict actuel), badges neutres et revalidation bornée. **#440 fusionnée : correction qualité**, à requalifier sur le SHA déployé ; réception Cloud/TrueNAS **NOT_VERIFIED**. Un cache de 7 jours correspond à un historique consultable, jamais à une preuve de disponibilité actuelle. Les transitions F03/F09 requièrent un inventaire daté (source, fenêtre, TTL, autorisation, identité) avant tout verdict. Produire, sur un SHA et un environnement identifiés, un rapport de couverture et de fraîcheur par source, avec les cas de refus, absence et panne distingués. Les 67,9 % evidence / 7,1 % healthy du 05/11 restent une **ancienne mesure**, non une situation actuelle. [Couverture](runbooks/cloud-probe-evidence-coverage.md) et [acceptation](runbooks/fastapi-observability-acceptance.md). |
| **F09 — Projections et intégrations** | Vue couches réseau/Cloudflare/Prometheus **CODED** ; **NOT_VERIFIED** au runtime ; priorité **P0.1** avec F03 | Valider cache L1/L2 Redis opt-in sans mélange d'environnements, critères `unknown/warn` et âge des preuves ; authentification scrape, pas de sonde WAN pfSense interdite. Vérifier cold/warm/revisit, âge du résumé PUBLIC et réception des sondes OWNER après nouvelle autorisation. **Résiduel H05** : **CODED sur PR #441** un historique Redis opt-in des seules sondes directes exécutées, par scope, 7 jours max, OWNER vérifié et sans données privées dans localStorage ; [contrat et recette](runbooks/owner-last-known-probe-history.md). **Restent ouverts** Gatus/Prometheus/TrueNAS non directs, `entityRef`/provenance, réception serveur après déploiement, expiration et budget Cloud ; **correctif de suivi #441** : cycle de vie du panneau historique OWNER (effacement à l'expiration/révocation, rejet des réponses en vol, nouvelle lecture après autorisation) **CODED**, réception navigateur **NOT_VERIFIED** ; ni 403 ni absence de sonde ne prouvent DOWN. **Diagnostic workstation ciblé** : `bash scripts/agent-diagnostics.sh --metrics-lan` ou `--metrics-both`, revue à blanc `--plan`; code et tests offline **CODED**, mesures réelles **NOT_RUN**. Un 401/403, une absence de métrique ou un cache expiré ne prouvent pas DOWN. [Connexions](runbooks/truenas-cloud-connection-probes.md). |
| **F11 — Catalogue Backstage V2 et affichage** | **CODED**, réception **NOT_VERIFIED** : [Compose #365](https://github.com/AlbanAndrieu/nabla-compose/pull/365) et [FastAPI #424](https://github.com/AlbanAndrieu/fastapi-sample/pull/424) et [#432](https://github.com/AlbanAndrieu/fastapi-sample/pull/432) fusionnées ; 139 liaisons runtime V2 récupérées dans le snapshot, cartes publiques enrichies, recette runtime **NOT_VERIFIED**. | Vérifier la parité de `catalogRevision` depuis Compose jusqu'à `/api/site/catalog/v2`, `/api/site/health/v2`, `/api/homelab-services` et `/sickz` sur SHA déployé. Afficher type/tags sans URL/IP/port dans les cartes publiques ; réserver exposition, owner et sondes détaillées à OWNER. Retirer le legacy seulement après migration Site Alban et preuve de parité. **16/11** : `/api/site/catalog/v2` et `/api/site/health/v2` répondent 401 sans jeton SERVICE (Cloud et TrueNAS), et `/api/homelab-services` n'expose pas `catalogRevision` : parité **NOT_RUN** faute de jeton site sur la workstation. [Décision et recette](archive/2026-11-14-catalog-v2-roadmap-alignment.md). |
| **F01 — Cloud UI et OWNER** | **CODED** (#382, #383, #390), recette récente **NOT_VERIFIED** | Attester `/v2/version` sur Cloud et TrueNAS, tester dans Chromium `/api`, `ui_safe=1`, `ui_full=1`, `operator=1` et combinaison OWNER ; absence de gel JS, défilement du panneau TrueNAS, aucun détail privé anonyme. **Recette partielle du 16/11 (17:10 UTC, workstation)** : `/v2/version` = `1.37.2` sur Cloud et TrueNAS (release de `master` 9bc6d212), mais `build_revision` vaut `null` : le SHA servi n'est pas attesté. Chrome anonyme sur Cloud, `/api?ui_safe=1` et `/api?ui_full=1&operator=1` : aucune erreur console, boucle JS sans retard sur 10 s, aucune IP privée affichée. Restent **NOT_RUN** : TrueNAS dans le navigateur (l'extension refuse l'IP LAN ; `curl` répond 200), session OWNER et défilement du panneau TrueNAS. [Recette](runbooks/fastapi-truenas-owner-acceptance-20261029.md). |
| **F02 — FinOps FastAPI Cloud Nano** | **CODED** : PR [#419](https://github.com/AlbanAndrieu/fastapi-sample/pull/419) fusionnée le 11/11 ; **NOT_VERIFIED** en production | Mesurer le **CPU vCPU**, la RAM, les réplicas et latences dans FastAPI Cloud Metrics avant/après à trafic comparable. Vérifier polling OWNER 180 s, absence de polling public, profilage Cloud inactif par défaut, cgroup v2 à la demande. Ne pas confondre CPU processus, cAdvisor TrueNAS et métriques de facturation. [Budget runtime](runbooks/fastapi-cloud-runtime-cost-guard.md). |
| **F04 — Qualité et publication locale** | Corrections CI et gates **CODED** ; HEAD actuel **NOT_VERIFIED** | `just ui-quick` puis L2 (`scripts/agent-quality-gate.sh --fix`) et L3 (`scripts/agent-publish.sh`) au SHA exact ; vérifier les suites et obtenir **deux runs master** consécutifs réels avant de clôturer [issues/355](https://github.com/AlbanAndrieu/fastapi-sample/issues/355). Aucun FAIL/timeout converti en PASS. **16/11** : `just ui-quick` échouait sur `master` (2 tests : bac à sable `vm` sans `CustomEvent` depuis #442, événement émis sans `detail` depuis #440) ; harnais corrigé, 50/50. [Qualité](../.agents/skills/local-first-quality/SKILL.md). |
| **F05 — Identité publique et accès** | Cible `fastapi-sample.albandrieu.com` **CODED** ; DNS final **NOT_VERIFIED** | `nabla-compose` possède l'apply OpenTofu, la route Tunnel et Access. FastAPI vérifie séparément santé LAN, réponse 302/403 Access, CDN/WAF, Cloud et DNS `dns_sample` ; ne pas exempter le WAF pour faire passer une sonde. **16/11 (17:10 UTC)** : le nom résout vers Cloudflare (proxied) et `/`, `/health`, `/api` répondent 302 vers `albandrieu.cloudflareaccess.com` ; santé LAN 200. Restent `dns_sample` et CDN/WAF. [Contrat réseau](fastapi-sample-cloudflare-network-contract.md). |

**Done P0** : SHA effectivement servi, OWNER et anonymous recettés sur navigateur, budget observé et sondes expliquées avec leur fraîcheur ; **F11** réclame une parité Backstage V2 séparée. Aucun droit supplémentaire implicite.

## P1 — Qualité de l'observabilité et expérience opérateur

| ID | État | Preuve et prochaine action |
| --- | --- | --- |
| **F06 — Accueil Operations Overview** | Démonstration météo remplacée dans [#396](https://github.com/AlbanAndrieu/fastapi-sample/pull/396), **CODED** ; runtime **NOT_VERIFIED** | Confirmer rendu sans clic, caches publics sans information OWNER, froid/chaud et mode déconnecté ; la démo est uniquement sur `/demo/sensors`. [Transition](runbooks/home-operations-transition.md). |
| **F07 — Heatmap et ressources** | Tri cAdvisor CPU/RAM/FS/RX+TX [#418](https://github.com/AlbanAndrieu/fastapi-sample/pull/418) fusionné ; **CODED**, recette OWNER **NOT_RUN** | Test Node, session OWNER mobile et anonyme, `0` mesuré distinct de l'absence `—`, échelle max sur les lignes visibles ; compléter occupation **ZFS dataset** sans l'inférer de `container_fs_usage_bytes`, NetFlow/Sankey seulement avec flux sourcés. [Transition](runbooks/home-operations-transition.md). |
| **F08 — Runtime TrueNAS et démarrage** | PostgreSQL `fastapisample` TLS 1.3/`verify-full` et réception Sentry documentés le 13/11 côté Compose ; démarrage lent encore ouvert | Isoler trois pauses d'environ 1 min avant Unleash, Logfire et Sentry ; instrumenter par phase avec borne de durée, vérifier `/health`, `/readyz`, les sondes Prometheus et le chemin LiteLLM/OpenRAG sans régression. **Instrumentation CODED 16/11** ([`startup_phases.py`](../nabla/startup_phases.py)) : chaque phase de `create_app` (Datadog, rate limiting, Unleash, métriques, routeurs, Logfire, Sentry, MCP…) journalise `startup_phase` avec sa durée, en WARN au-delà de 5 s, plus `process_start_to_create_app` pour les imports. À lire au prochain redémarrage TrueNAS (**NOT_RUN**). **Déploiement et APP ID appartiennent à Compose**. [Runbook](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/runbooks/fastapi-sample-truenas-diagnostics.md). |
| **F12 — Observateur : bleu « attendu » et stabilité** | État `expected` (bleu) pour les échecs voulus (route interne, API pfSense coupée sur Cloud) et un seul écrivain par badge, mises à jour en place : **CODED** (branche `fix/observer-expected-blue-20261113`), vérifié sur instantanés Cloud et TrueNAS capturés le 13/11 ; runtime **NOT_VERIFIED** | Après déploiement : `/api?ui_full=1&operator=1` sur Cloud et TrueNAS, aucun badge qui change de couleur ou de taille au rafraîchissement, tiroir sans clignotement. Côté Compose : nom d'hôte V2 LiteLLM et `tunnelUrl` obsolète, application Access LiteLLM résiduelle, `litellm-albandrieu` joignable (403) depuis Cloud, liaison runtime Redis absente. |
| **F13 — Fenêtre nocturne : état violet `scheduled`** | Une route dont l'entité porte `albandrieu.com/operational-schedule: night` et qui n'est pas `ok` hors de 01:00-07:00 (Europe/Paris, lundi-samedi, miroir de `reconcile-night-window-cron.py` de nabla-compose) passe en `scheduled` (violet) au lieu de `fail`, aussi dans `site_health_v2` et `ui_public_services` : **CODED** ([#444](https://github.com/AlbanAndrieu/fastapi-sample/pull/444) fusionnée, release 1.38.0), tests unitaires ; runtime **NOT_VERIFIED** | Après fusion du label dans nabla-compose (PR #397) et déploiement : `/api?ui_full=1&operator=1` sur TrueNAS et Cloud de jour (bitcoind, paperless en violet) et de nuit (état normal). **16/11** : `home-operations` (une ligne `scheduled` faisait disparaître tout le panneau flotte, `projectFleet` rejetant l'état) et la topologie gardent le violet, **CODED** avec tests. `connection_matrix` ne reçoit aucune App nocturne : inchangée. Reste : les arêtes requises et le `dependency_state` des dépendants sont calculés avant `mark_scheduled_off_window`, ils peuvent encore afficher un échec de jour. |
| **F14 — États incohérents du 16/11** | 47 cartes TrueNAS sur 147 incohérentes avec le runtime ; **6 défauts sur 8 CODED le 16/11** (tests unitaires), runtime **NOT_VERIFIED** | **Corrigés** : `planned`/`disabled` (label `albandrieu.com/operational-state`) qui ne répondent pas passent en gris « Not deployed » (`mark_not_deployed`) ; une liaison ambiguë (Redis, deux Apps avec un conteneur `redis`) est `unknown`, plus « manquante », et ne dégrade plus ses 8 dépendants ; le refus de connexion d'une route avec `probePath` (keycloak, prometheus…) donnait `unknown` faute de jointure : jointure par `id` ; Cloud : 403 Access Default-Deny d'un service privé = DENIED (`ok`, origine non atteinte), plus « exposé » ; 5xx renvoyé par l'origine après Access (Uptime Kuma) = `fail`, et `ORIGIN_ERROR` passe avant `ACCESS_PROTECTED` ; erreur d'observateur Cloudflare (`AuthenticationError`) = `unknown` par service, plus 23 `warn`. **Restent ouverts** : (1) jobs `Exited (0)` (`defectdojo-initializer`, `homarr-sync`) en `warn` : TrueNAS ne transmet pas le code de sortie, et passer `EXITED` en `ok` risquerait un faux vert ; vérifier sur `app.query` si un code non nul devient `crashed`, et marquer les jobs one-shot dans nabla-compose (`homarr-sync` est déclaré `controller`) ; (2) route `*.int` (hello-nginx) sondée en WAN : construire `internal_endpoint_url` dans `CatalogRoute` et sonder en HTTP depuis TrueNAS, la sonde WAN restant celle de Cloud ; (3) ajouter `appId: redis` à la liaison dans nabla-compose. Recette : `/api?ui_full=1&operator=1` sur TrueNAS et Cloud après déploiement. |
| **F10 — Scans et DefectDojo** | Endpoints et export privés préparés, import **NOT_VERIFIED** | Product/engagement et RBAC limités, import LAN sans secret, suivi asynchrone jusqu'à `Processed`, déduplication et refus inter-produit ; coordination avec les ressources Compose, sans importer des secrets en CI. [Import privé](runbooks/defectdojo-fastapi-private-import.md). |

**Done P1** : couverture sans fausses classifications, interface mobile utilisable, sondes et métriques attribuées à leur source, aucun secret émis dans le navigateur.

## P2 — Architecture, sécurité et dette technique

- **RoutePolicy/ASGI/JWT** : HTTP, WebSocket, MCP/A2A et consommateurs PUBLIC/SERVICE/OWNER/INTERNAL ; éprouver JWKS/JWT, mauvais issuer/audience, perte JWKS et route denial avant `OPS_ROUTE_POLICY_STRICT`. **Non activé par simple refactoring.** 16/11 : perte JWKS testée (un échec n'est jamais mis en cache, refus 503 fail-closed) ; mauvais issuer/audience, signature, `nbf`, `kid` et jeton de service étaient déjà couverts. Reste la recette MCP/A2A avant d'activer le mode strict.
- **OIDC Keycloak** : identité FastAPI distincte de PostgreSQL OAuth, gestion MFA et révocation ; architecture et exposition Keycloak appartiennent à Compose.
- **Fédération TrueNAS → Cloud** : agrégats signés, datés, minimisés et authentifiés ; aucun accès LAN depuis Cloud, aucune IP privée ni secret dans un DTO public.
- **Qualité des scripts** : `scripts/ci/quality-git.sh` pour la base Git, `quality-lock.sh` pour `flock -o`, `quality-timeout.sh` pour les échéances, `run-pytest-bounded.sh` pour la CI. Conserver le rapport lisible `run-pytest-compact.sh` pour les sessions locales. **Ne pas refusionner ces CLI dont les contrats de sortie diffèrent**. Retirer les hooks dupliqués prek/ruff/gitlint uniquement après tests ciblés. 16/11 : l'alias `ruff` (second lint avec `--unsafe-fixes`) et `gitlint-ci` (argument fictif `mybranch`) sont retirés ; `ruff-check --fix` reste seul, contrat testé.
- **Maintenance** : Renovate et Helm sans automerge, qualité Python et Node, revue des tests et règles sécurité de PR. Les chantiers anciens non requalifiés restent dans [engineering-backlog.md](engineering-backlog.md), jamais automatiquement P0.

## Travaux terminés et documents de preuve

Les livraisons **CODED** déjà fusionnées (#382, #383, #390, #396, #418, #419) ne doivent plus être planifiées comme implémentations à refaire : seules leurs **recettes sans preuve** restent dans F01–F09. Les mesures et dysfonctionnements d'octobre ne sont pas l'état courant.

Historique : [réconciliation V2 du 14/11](archive/2026-11-14-catalog-v2-roadmap-alignment.md), [archive avant consolidation](archive/2026-10-29/engineering-roadmap-before-consolidation.md), [registre d'incidents](incidents.md), [journal de réconciliation du 13/11](archive/2026-11-13-roadmap-reconciliation.md), [guide documentation](README.md).

**Souveraineté :** FastAPI possède API, endpoints, statuts, auth des routes, tests et interface ; Compose possède TrueNAS, secrets, Cloudflare, Gatus et Prometheus ; Site Alban possède le rendu Next.js. Toute validation affirme son environnement, son SHA et sa date.

### 2026-11-19 — F11 / production DAST acceptance

- Previous catalog PRs #447, Compose #412 and Site #329 merged. Compose #416 adds a revision-bound operator inventory preserving native graph metadata and migrates TrueNAS lifecycle/recovery consumers; this FastAPI branch reads that v2 projection and refreshes the paired snapshots. Retain old Compose exports until dependency rollout, plan-replay and runtime acceptance. No runtime acceptance claimed.
- 18 November post-merge run 44396811271: Python tests passed, browser smoke failed during Playwright installation, ZAP not run. Older ZAP preflights failed without Cloudflare credentials. `/api` is HTML, not JSON.
- Dedicated GitHub environment `dast-truenas` (master only), with `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` from a dedicated Cloudflare Service Auth policy. Cloud DAST has its own job without credentials. No diagnostics key or OWNER cookie for the production scan. Exact-host Replacer scope, no preflight redirects and clean temporary credentials. Review artifact handling before granting the token; active OpenAPI scan remains as before and must be run only with an approved scope. Full active scan should target isolated staging with a test account and no production data.
- Acceptance: provision the environment/policy, check production HTML/OpenAPI preflight, run manual ZAP on master, inspect actual reports (not-run is not pass), validate provider policy and topology parity. Owner: infrastructure + FastAPI, runtime NOT_RUN.
