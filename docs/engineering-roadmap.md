# Roadmap active — FastAPI Sample

**Révisée le 30 octobre 2026.** Ce document ne liste que les travaux
**non acceptés** et leur prochaine preuve. Les preuves datées sont dans
[le registre d'incidents](incidents.md), les commandes dans
[les runbooks](README.md) et les demandes anciennes à requalifier dans
[le backlog historique](engineering-backlog.md).

**États :** `CODED` = présent dans Git ; `TESTED` = testé sur un SHA exact ;
`DEPLOYED` = SHA/image identifié sur l'environnement ;
`ACCEPTED` = comportement constaté sur cet environnement.
`NOT_RUN`, `UNVERIFIED`, `DENIED` et un merge ne sont pas des succès runtime.

## Vue d'ensemble et ordre d'exécution

Priorité propriétaire (31/10) : (1) recette navigateur Cloud avec SHA
attesté, (2) Gatus/Prometheus ; le reste suit.

| Priorité | Chantier | Dernière preuve vérifiable | Prochain jalon |
| --- | --- | --- | --- |
| **P0 (1)** | Recette navigateur | 31/10 Cloud `1.26.3` : `?ui_full=1` gèle le thread (boucle `MutationObserver` du drawer, cause prouvée par pile CDP) ; correctif fusionné ([#390](https://github.com/AlbanAndrieu/fastapi-sample/pull/390), `5f6b6fff`) ; `build_revision` Cloud `null` | Déployer `5f6b6fff`, rejouer les 5 modes Chromium sur l'image et attester le SHA |
| **P0 (2)** | Gatus / Prometheus | 85 sondes déclarées, **61 UP / 24 DOWN** historiques (26/10) ; `up{job="fastapi_sample"}=1` signalé le 30/10, 22/28 targets globalement UP | Comparer état et fraîcheur par service, confirmer auth scrape et corriger les exporters défaillants |
| **P0** | UI Cloud riche + OWNER, [PR #383](https://github.com/AlbanAndrieu/fastapi-sample/pull/383) fusionnée le 30/10 | `just ui-quick` **37/37 PASS** au SHA `cb43c27b` sur TrueNAS et workstation ; L2 a modifié six JS lors du formatage | Revoir le diff, publier les corrections sur la PR, L1/L2/L3 sur le HEAD final |
| **P0** | Qualité de `master` et [#355](https://github.com/AlbanAndrieu/fastapi-sample/issues/355) | Sur `7fbd2f61` : 28 échecs pytest ; correctifs **1879 pytest + 35 Node PASS** et L2 PASS sur une branche de travail distincte, non équivalents à une preuve actuelle de `master` | Gate complète au HEAD candidat, puis deux runs master réussis avant clôture de #355 |
| **P1** | OWNER mobile + TrueNAS Docker | Ancien build `0266f20d` refusé en étape 3/6 ; dernière recette réussie `fa13c08d` | Classer le journal privé, accepter un build 6/6 récent, puis session OWNER authentifiée en HTTPS |
| **P1** | Cartes et graphe | UI et liens prévus dans le code, recette interactive non attestée | Navigation par ID canonique, filtres mobiles, états DNS/TCP/TLS/HTTP/auth/métriques et horodatage |
| **P2** | Sécurité, intégrations et dépendances | Contrats, pilotes et tests partiels existants | Recettes RoutePolicy, traces, Renovate, DefectDojo, LiteLLM et documentation d'ownership |

## P0 — Livraison sûre du tableau Cloud et rétablissement de la qualité

- [x] **CODED :** PR [#382](https://github.com/AlbanAndrieu/fastapi-sample/pull/382)
  **fusionnée le 30/10**, avec catalogue léger, mode `ui_safe=1`,
  entrée OWNER et correctifs d'observateurs DOM. Fusion ≠ déploiement.
- [x] **CODED, pas ACCEPTED :** [#383](https://github.com/AlbanAndrieu/fastapi-sample/pull/383)
  ordonne le chargement du contrôleur OWNER avant les imports riches,
  conserve le catalogue et refuse toute élévation de droits par URL.
- [x] **TESTED L1 :** `just ui-quick` 37/37 PASS sur `cb43c27b` ;
  autres preuves de l'ancien HEAD restent historiques. Aucun Chromium E2E
  sur l'image Cloud actuelle.
- [ ] **L2 :** revoir les **six fichiers JS** modifiés par pre-commit dans
  le worktree isolé ; ne pas les écraser. Publier uniquement les
  corrections approuvées en `[skip ci]`, puis exécuter `just ui-quick`
  et `bash scripts/agent-quality-gate.sh --fix` avec Node **et npm**.
  L2 était bloqué par `nodeenv`, puis par npm manquant sur TrueNAS,
  puis interrompu par le formatteur sur workstation ; aucun bypass.
- [ ] **L3 :** sur un HEAD propre, exécuter `bash scripts/agent-publish.sh`,
  sans GitHub Actions. Contrôler les rapports du SHA exact et la sécurité.
- [ ] **Recette Cloud :** identifier l'image/SHA effectivement déployé,
  mesurer en vrai Chromium `/api`, `?ui_safe=1`, `?ui_full=1`,
  `?operator=1` et `?operator=1&ui_full=1` (avant/après session).
  Séparer `main_thread_unresponsive`, `ui_loading_without_content`
  et `http_access_restricted`. **31/10 :** seul `?ui_full=1` est
  `main_thread_unresponsive` sur `1.26.3` ; cause et correctif dans
  [incidents](incidents.md). Reste : rejouer après déploiement, puis
  exposer un SHA Cloud (`/v2/version` rend `build_revision: null`).
- [ ] **Publication :** faire relire puis déployer via le circuit autorisé,
  sans merge ou déploiement automatique ; confirmer les interactions sur
  l'image déployée.
- [ ] **Qualité master :** vérifier la présence sur `master` des correctifs
  aux 28 anciens échecs et exécuter la suite complète. Ne fermer
  [#355](https://github.com/AlbanAndrieu/fastapi-sample/issues/355)
  qu'après deux runs réels `master` consécutifs verts. **31/10 :** sur
  `08f8f5f6` (1.26.3), 3 contrats échouaient (taille et fin de
  `api-health.js` après #383, phrases de roadmap) ; corrigés sur
  `fix/ui-full-drawer-observer-loop-20261031` avec 1884 pytest et
  `just ui-quick` 40/40, L2/L3 PASS sur le SHA de la PR. Reste : runs `master` au HEAD exact.

- [ ] **CI bornée et sécurité Actions (31/10) :** le workflow
  [master-red #65](https://github.com/AlbanAndrieu/fastapi-sample/actions/runs/41195829678)
  a échoué sur Zizmor : deux usages de `pypa/gh-action-pypi-publish`
  v1.14.2 vulnérable et six annotations `actions/setup-python` non exactes.
  La [PR #391](https://github.com/AlbanAndrieu/fastapi-sample/pull/391)
  est fusionnée : elle corrige ces références et borne les jobs via
  `timeout-minutes`, avec deadlines pour les suites pytest et tests de contrat.
  **CODED dans master** ; actionlint/Zizmor et gate L2/L3
  sur le commit final restent à vérifier sans gaspillage de CI. Les timeouts
  doivent donner un FAIL explicite, jamais un faux PASS. Après fusion,
  vérifier un run `master` complet et ne clôturer #355 qu'avec preuves.

**Done P0 :** tableau riche interactif sans gel ; accès OWNER disponible
sans import riche ; droits serveur préservés ; tests et SHA Cloud tracés ;
`master` réellement validé.

## P1 — Acceptation TrueNAS, observabilité et UX

- [ ] **TrueNAS :** classifier en lecture seule le build Docker échoué
  avant toute nouvelle construction, puis obtenir un 6/6 et identifier
  l'image en service. Cette opération appartient à
  [nabla-compose](https://github.com/AlbanAndrieu/nabla-compose).
  **31/10, 14:11 UTC :** depuis le LAN, `172.17.0.24:8091` refuse la
  connexion (hôte joignable sur 443/7000) ; `sample.albandrieu.com`
  renvoie 302 Cloudflare Access sur tous les chemins. Côté Cloud, Keycloak
  répond par la page challenge « Just a moment… » (403), distincte du
  Default-Deny : elle reste `reachable: false`. Cause du `:8091` : l'App
  TrueNAS `sample` a été supprimée, et `update-fastapi-sample.sh` échouait
  en `app.update` (`ENOENT App sample does not exist`). Correctif
  nabla-compose `fix/sample-update-creates-missing-app-20261031` :
  `app.create` si l'App manque. Preuve suivante : script 6/6 sur TrueNAS,
  `/health` 200 sur `:8091`, et challenge Keycloak classé.
- [ ] **OWNER mobile :** vérifier depuis une source approuvée le bouton
  `Unlock diagnostics`, `authenticated=true`, la session HTTPS et
  le refus hors LAN/allowlist ; `readOnlyDiagnostics=true` n'est pas OWNER.
  Distinguer 401 (clé), 403 (source/origine), 503 (configuration).
- [ ] **Gatus :** comparer 85 sondes historiques au catalogue réel, classer
  `UP / DOWN / NO_SAMPLE / MISSING_MONITOR / NOT_MONITORED`, confirmer
  leur fraîcheur et traiter les échecs sans les masquer.
- [ ] **Prometheus :** consolider la preuve du scrape
  `up{job="fastapi_sample"} == 1` avec authentification dédiée ;
  auditer Postgres/Redis/pfSense exporters. Un `401` anonyme sur
  `/metrics` est attendu, non une panne.
- [ ] **Cartes/Topologie :** rapprocher les IDs canoniques et les unités
  Garage S3/Admin/UI, garantir les liens upstream/downstream cliquables,
  détails `DNS → TCP → TLS → HTTP → auth → metrics`, origine des mesures,
  âge/staleness, statuts d'accès et parcours mobile/clavier.
- [ ] **Exposition :** distinguer Cloudflare Access `302/403`, sonde
  outside-in, état LAN, API pfSense et perte réelle d'un workload.
- [ ] **Sémantique santé TrueNAS (diagnostic 30/10, 20:30 UTC) :**
  `sample` RUNNING/`in_sync`, `/health` 200, mais `/healthz` `degraded`
  par le seul Keycloak (`403` Cloudflare Access Default-Deny, service
  différé) ; Pyroscope `/` 200 alors que `/ready` répond 503 ;
  `/v2/version` = 1.25.0 avec `build_revision=null` (`master` 1.26.0).
  **CODED/TESTED (non commité, non déployé) :** Keycloak Default-Deny
  classé `unknown`/warn, sonde Pyroscope sur `/ready` (révèle
  « Metastore not ready »), argument Docker `BUILD_REVISION`, build arg
  `FASTAPI_SAMPLE_BUILD_REVISION` dans `compose.yml` et, dans `release.yml`,
  `BUILD_REVISION` = `git rev-parse HEAD` du tag extrait (`github.sha` est
  le HEAD par défaut du dispatch, pas le tag). Restent : export du SHA par
  `scripts/truenas/update-fastapi-sample.sh` (nabla-compose), gate L2/L3.
  Preuve suivante : `/v2/version` avec SHA complet sur TrueNAS et sur
  l'image GHCR de la prochaine release (label
  `org.opencontainers.image.revision` = commit du tag), `/healthz` sans
  Keycloak en échec, Pyroscope `/ready` 200 après réparation du metastore.
- [ ] **Compose unique et hostname public (31/10) :** nabla-compose supprime
  `apps/sample/` et déploie ce `compose.yml` via son sous-module
  `apps/fastapi-sample` ; hostname public `sample.albandrieu.com` →
  `fastapi-sample.albandrieu.com` (interne `sample.int.albandrieu.com`,
  App `sample` et secrets inchangés). Ordre : fusionner cette PR, puis
  pointer le sous-module nabla-compose sur son commit. DNS, route tunnel et
  Access Cloudflare passent en OpenTofu dans une PR nabla-compose séparée.
  Preuve suivante : `update-fastapi-sample.sh` 6/6, puis
  `https://fastapi-sample.albandrieu.com/health` 200 via Access ; la
  campagne ZAP pointe vers ce hostname.
- [ ] **Réconciliation TrueNAS (même diagnostic, owner
  [nabla-compose](https://github.com/AlbanAndrieu/nabla-compose)) :**
  `unbound` requis `unknown` (timeout API pfSense `services`),
  `uptime-kuma` public `502`, 3 `binding_conflict` (`hello-nginx` et
  `sentry-edge` sur le même `nginx`, `redis` multiple), 41 `declared_only`
  / 41 `observed_only` dont écarts de nom (`homeassistant`,
  `elasticsearch`, `hermes`, `graylog`). Preuve suivante : bindings
  uniques, noms alignés, `unbound` et `uptime-kuma` OK avec preuve fraîche.
- [ ] **Comparaison des sondes Cloud / TrueNAS / local (04/11, 19:10–19:20 UTC,
  `v0+1.27.0`, `build_revision=null` partout) :** lecture seule, GET
  séquentiels. **TrueNAS `NOT_RUN`** depuis un conteneur cloud :
  `sample.int` sans DNS public, `sample.albandrieu.com` → 302 Access
  (attendu), `fastapi-sample.albandrieu.com` sans enregistrement DNS. Vue
  indirecte via Cloud : App `sample` RUNNING/`in_sync`, image
  `fastapi-sample:local`, **aucune sonde HTTP** de cette instance.
  Cloud : `/readyz` ready, `/healthz` et `/api/homelab/health` `degraded`,
  cache 30 s (froid 3–6,5 s, chaud ≈0,7 s). Constats à traiter :
  (a) `/sickz` public, sans cache ni limite SlowAPI, ≈68 groupes sondés par
  requête, 8,6–11 s de bout en bout (fan-out 8 s puis enrichissement
  séquentiel ≤6 s) ; (b) posture pfSense Cloud en `ConnectTimeout` alors que
  WAN 10443 est volontairement fermé à Cloud (nabla-compose) : phase de
  6,1 s à chaque tentative d'origine (demi-ouverture, au plus toutes les
  900 s), 27 ms quand le disjoncteur la supprime ; Service Token refusé
  par Access pour adguardhome, affine, freshrss et keycloak ; joplin sans
  DNS (déclaré `external=true`) ; (c) sonde Tavily avec
  la requête `"."` rejetée (`Query is invalid.`) ; (d) OVH `openstack_me` :
  credential inexistant côté Cloud (rotation opérateur) ; (e) depuis l'egress
  Cloud, Keycloak reçoit le challenge Cloudflare (403) et LiteLLM 403 sur
  les trois chemins, alors que `/health/liveliness` répond 200 depuis un
  autre egress externe ; (f) owner nabla-compose : `hello.int` (200) et
  `s3.int` (403 S3) joignables depuis Internet via l'IP WAN, sans Cloudflare,
  Vaultwarden en bypass Access « Everyone » sur tout le hostname, Homarr
  CRASHED, Graylog/Lidarr STOPPED (Lidarr avec ingress tunnel). Preuve
  suivante : même campagne depuis le LAN (TrueNAS `:8091` + workstation),
  `/sickz` mis en cache ou limité, `PFSENSE_AUTHENTICATED_PROBES_ENABLED`
  aligné sur la politique WAN, Tavily/OVH verts, `*.int` refusés au
  frontal WAN hors exceptions revues.
  **CODED/TESTED L1 (non déployé) :** (a) cache `/sickz` 60 s single-flight
  (`nabla/api/sickz_cache.py`, purge avec `/api/health-board/cache/reset`) ;
  (c) sonde Tavily via `GET /usage` (`nabla/api/tavily_health.py`) ;
  (e) page challenge Cloudflare classée `warn`/non vérifiée pour Keycloak et
  LiteLLM ; skill `fastapi-cloud` et doc pfSense alignés sur
  `PFSENSE_AUTHENTICATED_PROBES_ENABLED=false` côté Cloud. Restent opérateur
  (runbook nabla-compose `docs/runbooks/2026-11-04-probe-remediation.md`) :
  apply des routes Tunnel, Service Auth Access, bypass Vaultwarden par
  chemins, OVH, Graylog/Lidarr/Homarr/bitcoind, déploiement TrueNAS de
  dependency-track, netbox, scanopy, joplin, ntopng et plumber, migration
  canonique Home Assistant. Preuve suivante : déploiement Cloud au SHA de
  cette PR, `/sickz` en `probe_cache.source=cache` au 2ᵉ appel, `/healthz`
  sans `Query is invalid.`.
  **05/11 :** `PFSENSE_AUTHENTICATED_PROBES_ENABLED=false` appliqué sur Cloud
  (constaté : `transport_only`, `telemetry_disabled`) ; smoke de production
  aligné sur ce contrat. Décision propriétaire : **pas d'exception WAF** ;
  Keycloak/LiteLLM restent `warn` (`edge_block=challenge`) depuis Cloud, la
  preuve de santé vient de l'observateur TrueNAS LAN.

**Done P1 :** affichage détaillé non bloquant sur smartphone, OWNER
authentifié, aucun voyant vert sans preuve fraîche, couverture explicable
pour chaque service et refus WAN correct.

## P2 — Travaux différés après stabilisation

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

- [ ] **P1 — Remplacer la démonstration météo de `/` (04/11, CODED) :**
  page `Operations Overview` sans base PostgreSQL ; sondes et sécurité
  depuis le health-board ; CPU/mémoire/débit cAdvisor depuis la topologie ;
  latence HTTP mesurée sans prétention de RTT ; courbes de l'onglet uniquement.
  `/demo/sensors` conserve les anciens diagrammes en démo explicite ;
  génération synthétique retirée du startup. Accès propriétaire requis
  pour les informations détaillées, anonymes limités au répertoire public.
  **Reste :** valider les contrats route HTML/JS, Node 22, pytest et L2/L3,
  comparer le rendering desktop/mobile et vérifier TrueNAS/CLOUD.
  Voir [runbook](runbooks/home-operations-transition.md).

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
