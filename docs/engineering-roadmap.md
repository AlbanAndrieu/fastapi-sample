# Roadmap active — FastAPI Sample

> **Réconciliation du 13 novembre 2026.** Ce document suit exclusivement les travaux FastAPI **non acceptés**. Vue de décision transversale : [portefeuille Homelab](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap-portfolio.md). Configuration TrueNAS, CSI, pfSense, Cloudflare Tunnel et secrets : [roadmap nabla-compose](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap.md).

Une PR fusionnée n'est pas une acceptation runtime. Utiliser `CODED` (code fusionné), `TESTED` (tests exécutés sur SHA exact), `DEPLOYED` (image/SHA déployé identifié), `ACCEPTED` (comportement constaté sur cette image), `NOT_RUN` et `NOT_VERIFIED` (absence de preuve). Les refus Cloudflare `DENIED` et les diagnostics non exécutés ne sont pas `DOWN`.

## Rattachement au portefeuille Homelab unique

L'ordre **déjà validé** est **H01 → H02 → H05** : H01 (CSI Talos) et H02 (restauration PostgreSQL) appartiennent à Compose ; FastAPI ne prétend pas valider ces opérations. Le portefeuille [H01–H19](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap-portfolio.md) est l'unique arbitrage entre dépôts.

| Homelab | Actions FastAPI à réceptionner | Propriétaire de la mutation |
| --- | --- | --- |
| **H05** | **F03** (couverture + fraîcheur), **F09** (connexion Cloud/TrueNAS) ; preuves Gatus/Prometheus | Compose pour les exporters et cibles, FastAPI pour la projection |
| **H06** | **F01** (UI/OWNER), **F02** (FinOps Cloud Nano) | FastAPI, sans réveil ou exposition supplémentaire |
| **H04** | **F05** (DNS/Access), preuves négatives | Compose pour DNS/Tunnel/Access |
| **H14** | **F06–F07** (Operations Overview, heatmap OWNER) | FastAPI et sources mesurées côté Compose |
| **H17** | **F11** (catalogue V2 et suppression ordonnée des vues legacy) | Compose → FastAPI → Site Alban |
| **H19** | Aucune bascule Home Assistant dans FastAPI | Compose |

Les anciens identifiants **E01–E14** de #423 sont conservés comme [table de correspondance en archive](archive/2026-11-13-roadmap-reconciliation.md), pas comme seconde roadmap active. Aucun passage de `CODED` à `ACCEPTED` sans preuve runtime datée.

## P0 — Recette de production, sécurité et budget

| ID | État code au 13/11 | À faire et critère de clôture |
| --- | --- | --- |
| **F01 — Cloud UI et OWNER** | **CODED** (#382, #383, #390), recette récente **NOT_VERIFIED** | Attester `/v2/version` sur Cloud et TrueNAS, tester dans Chromium `/api`, `ui_safe=1`, `ui_full=1`, `operator=1` et combinaison OWNER ; absence de gel JS, défilement du panneau TrueNAS, aucun détail privé anonyme. [Recette](runbooks/fastapi-truenas-owner-acceptance-20261029.md). |
| **F02 — FinOps FastAPI Cloud Nano** | **CODED** : PR [#419](https://github.com/AlbanAndrieu/fastapi-sample/pull/419) fusionnée le 11/11 ; **NOT_VERIFIED** en production | Mesurer le **CPU vCPU**, la RAM, les réplicas et latences dans FastAPI Cloud Metrics avant/après à trafic comparable. Vérifier polling OWNER 180 s, absence de polling public, profilage Cloud inactif par défaut, cgroup v2 à la demande. Ne pas confondre CPU processus, cAdvisor TrueNAS et métriques de facturation. [Budget runtime](runbooks/fastapi-cloud-runtime-cost-guard.md). |
| **F03 — Couverture des sondes** | Calculs et classifications **CODED**, preuve fraîche **NOT_VERIFIED** | Rapprocher `entityRef`/`catalogRevision`, Gatus, Prometheus et observation directe ; exposer `UP`, `DOWN`, `NO_SAMPLE`, `NOT_MONITORED`, `DENIED`, `STALE` sans faux vert. Les 67,9 % evidence / 7,1 % healthy du 05/11 restent une **ancienne mesure**, non une situation actuelle. [Couverture](runbooks/cloud-probe-evidence-coverage.md) et [acceptation](runbooks/fastapi-observability-acceptance.md). |
| **F04 — Qualité et publication locale** | Corrections CI et gates **CODED** ; HEAD actuel **NOT_VERIFIED** | `just ui-quick` puis L2 (`scripts/agent-quality-gate.sh --fix`) et L3 (`scripts/agent-publish.sh`) au SHA exact ; vérifier les suites et obtenir **deux runs master** consécutifs réels avant de clôturer [issues/355](https://github.com/AlbanAndrieu/fastapi-sample/issues/355). Aucun FAIL/timeout converti en PASS. [Qualité](../.agents/skills/local-first-quality/SKILL.md). |
| **F05 — Identité publique et accès** | Cible `fastapi-sample.albandrieu.com` **CODED** ; DNS final **NOT_VERIFIED** | `nabla-compose` possède l'apply OpenTofu, la route Tunnel et Access. FastAPI vérifie séparément santé LAN, réponse 302/403 Access, CDN/WAF, Cloud et DNS `dns_sample` ; ne pas exempter le WAF pour faire passer une sonde. [Contrat réseau](fastapi-sample-cloudflare-network-contract.md). |
| **F11 — Catalogue Backstage V2** | **CODED**, réception **NOT_VERIFIED** : `x-nabla.exposure` et relations `entityRef` fusionnées dans [Compose #365](https://github.com/AlbanAndrieu/nabla-compose/pull/365) ; consommateur [FastAPI #424](https://github.com/AlbanAndrieu/fastapi-sample/pull/424) **fusionné le 13/11** | Après fusion de #424 : comparer `catalogRevision` sur `/api/site/catalog/v2`, `/api/site/health/v2`, `/api/homelab-services` et `/sickz` ; vérifications LAN et Cloud sans fausse exposition pfSense ou Garage Admin. Supprimer le point d'entrée legacy **seulement après** migration Site Alban. [Contrat](gatus-python-monitoring-convergence.md). |

**Done P0** : SHA effectivement servi, OWNER et anonymous recettés sur navigateur, budget observé et sondes expliquées avec leur fraîcheur ; **F11** réclame une parité Backstage V2 séparée. Aucun droit supplémentaire implicite.

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

**Souveraineté :** FastAPI possède API, endpoints, statuts, auth des routes, tests et interface ; Compose possède TrueNAS, secrets, Cloudflare, Gatus et Prometheus ; Site Alban possède le rendu Next.js. Toute validation affirme son environnement, son SHA et sa date.
