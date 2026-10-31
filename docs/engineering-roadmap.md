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

| Priorité | Chantier | Dernière preuve vérifiable | Prochain jalon |
| --- | --- | --- | --- |
| **P0** | UI Cloud riche + OWNER, [PR #383](https://github.com/AlbanAndrieu/fastapi-sample/pull/383) fusionnée le 30/10 | `just ui-quick` **37/37 PASS** au SHA `cb43c27b` sur TrueNAS et workstation ; L2 a modifié six JS lors du formatage | Revoir le diff, publier les corrections sur la PR, L1/L2/L3 sur le HEAD final |
| **P0** | Recette navigateur | 31/10 Cloud `1.26.3` : `?ui_full=1` gèle le thread (boucle `MutationObserver` du drawer, cause prouvée par pile CDP) ; correctif validé par injection Chromium ; `build_revision` Cloud `null` | Déployer le correctif, rejouer les 5 modes Chromium sur l'image et attester le SHA |
| **P0** | Qualité de `master` et [#355](https://github.com/AlbanAndrieu/fastapi-sample/issues/355) | Sur `7fbd2f61` : 28 échecs pytest ; correctifs **1879 pytest + 35 Node PASS** et L2 PASS sur une branche de travail distincte, non équivalents à une preuve actuelle de `master` | Gate complète au HEAD candidat, puis deux runs master réussis avant clôture de #355 |
| **P1** | OWNER mobile + TrueNAS Docker | Ancien build `0266f20d` refusé en étape 3/6 ; dernière recette réussie `fa13c08d` | Classer le journal privé, accepter un build 6/6 récent, puis session OWNER authentifiée en HTTPS |
| **P1** | Gatus / Prometheus | 85 sondes déclarées, **61 UP / 24 DOWN** historiques (26/10) ; `up{job="fastapi_sample"}=1` signalé le 30/10, 22/28 targets globalement UP | Comparer état et fraîcheur par service, confirmer auth scrape et corriger les exporters défaillants |
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
  `just ui-quick` 40/40, L2 PASS. Reste : L3 et runs `master`.

**Done P0 :** tableau riche interactif sans gel ; accès OWNER disponible
sans import riche ; droits serveur préservés ; tests et SHA Cloud tracés ;
`master` réellement validé.

## P1 — Acceptation TrueNAS, observabilité et UX

- [ ] **TrueNAS :** classifier en lecture seule le build Docker échoué
  avant toute nouvelle construction, puis obtenir un 6/6 et identifier
  l'image en service. Cette opération appartient à
  [nabla-compose](https://github.com/AlbanAndrieu/nabla-compose).
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

**Done P1 :** affichage détaillé non bloquant sur smartphone, OWNER
authentifié, aucun voyant vert sans preuve fraîche, couverture explicable
pour chaque service et refus WAN correct.

## P2 — Travaux différés après stabilisation

- [ ] **RoutePolicy/ASGI :** couvrir HTTP, WebSocket, MCP/A2A,
  PUBLIC/SERVICE/OWNER/INTERNAL ; valider JWKS/JWT, consommateurs et
  clients externes avant `OPS_ROUTE_POLICY_STRICT` ou changement Access.
- [ ] **Observabilité transverse :** `traceparent` /
  `X-Nabla-Trace-ID` entre Site Alban et FastAPI ; réduire les
  duplications `platform_metrics.py`, `health_routes.py` et modules JS
  avec tests de non-régression.
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
