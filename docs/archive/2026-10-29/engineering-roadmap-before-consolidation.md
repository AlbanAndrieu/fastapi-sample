> Archive de référence (avant consolidation du 29 octobre 2026).
> Ce document conserve les anciennes tâches, preuves et commentaires sans les présenter comme l'état opérationnel courant.
> La roadmap active est [docs/engineering-roadmap.md](../../engineering-roadmap.md).

# Roadmap d'ingénierie — fastapi-sample

**État au 25 octobre 2026.** Cette page est l'unique roadmap
**active** de FastAPI Sample. Le détail avant consolidation est
[archivé sans perte](archive/2026-10-24/engineering-roadmap.md).
Les tâches anciennes non revérifiées demeurent dans le
[backlog historique](engineering-backlog.md) ; elles ne sont pas
automatiquement considérées ouvertes.

**Autorité** : FastAPI possède les endpoints, DTO, classifications de
probes, autorisations applicatives, collecte de preuves et UI `/api`.
[Compose](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap.md)
possède pfSense/Unbound, TrueNAS, exporter, secrets et déploiements.
[Site Alban](https://github.com/AlbanAndrieu/nabla-site-alban)
possède Next.js/Vercel, icônes et cache du navigateur.


## P1 prioritaire — Accès OWNER et drill-down sur smartphone LAN (28 octobre 2026)

**Observations opérateur :** sur Wi-Fi, `/api/ui/session` répond
`authenticated=false`, `readOnlyDiagnostics=true`, tandis que
`http://172.17.0.24:8091/api` est accessible. L'URL
`/api?operator=1` ne révèle pas `Unlock diagnostics` dans le runtime
observé. Cela démontre l'absence de session OWNER ; ce n'est pas un échec
de connectivité LAN. Le gel éventuel sur le smartphone n'est pas encore
prouvé par Chromium.

- [x] **PR #382 en Draft [skip ci] :** entrée `Owner access` dans HTML,
  panneau OWNER activé par le module léger sans importer les observateurs
  du dashboard avancé ; `operator=1` n'active plus `ui_full=1`.
- [x] **Contrat d'authentification maintenu :** clé, cookie signé HttpOnly,
  source/chaîne de proxy approuvées ; `readOnlyDiagnostics=true` ne
  devient jamais OWNER. Sur `ui_safe=1`, aucune connexion n'est montée.
- [x] **Session mobile :** revalidation sur `online`, `pageshow` et
  retour sur l'onglet ; état OWNER séparé de lecture seule ; aucune clé
  enregistrée dans le navigateur.
- [x] **Contrôles statiques :** 23/23 vérifications ciblées PASS sur les
  sources de la branche. Des tests Node de contrat sont ajoutés mais
  **non exécutés localement dans cette session**.
- [ ] **Recette locale :** exécuter Node/pytest sur un checkout #382,
  confirmer navigation HTML et affichage du bouton depuis smartphone.
- [ ] **Accès HTTPS :** après authentification effective, confirmer le
  cookie et distinguer HTTP 401 (clé) de 403 source/proxy/origine. Ne
  jamais supposer qu'une connexion Wi-Fi constitue une identité OWNER.
- [ ] **Cartes et drill-down :** après sélection volontaire de
  `ui_full=1`, prouver que DNS/TCP/HTTP/Gatus/Prometheus, le détail
  TrueNAS et les références downstream restent réactifs ; un gel du
  mode riche reste P0 séparé.
- [ ] **Build TrueNAS :** classifier le dernier journal privé Docker
  (classifieur déjà fusionné dans nabla-compose #289). Ne déployer le
  commit immuable #382 que lorsque la cause est comprise et le build
  accepté 6/6 ; aucun nouveau déploiement par cet agent.

**Décisions de publication :** #380 et #381 sont déjà fusionnées dans
fastapi-sample ; cela n'atteste pas leur présence sur TrueNAS. #382 est
encore Draft. Ne pas consommer de CI GitHub, ne pas fusionner
automatiquement et ne pas désactiver les ACL.

## P0 — Déchargement réel des modules UI lourds (28 octobre 2026)

- [x] **Analyse de la PR #381 :** le branchement `publicFirst` dans
  `api-health.js` n'empêchait pas ses **imports ESM statiques** de
  charger et évaluer les modules du tableau complet avant le test de mode.
  Cette faiblesse est démontrée dans le code ; une causalité avec le gel
  Chromium n'est pas encore prouvée.
- [x] **Correctif de code publié dans #381 [skip ci] :** le HTML de `/api`
  charge désormais `api-health-entry.js`, qui n'importe statiquement
  que `api-public-services.js`. `api-health.js` et son graphe de sondes,
  filtres et observateurs sont importés **dynamiquement** si `ui_full=1`
  ou `operator=1`. `ui_safe=1` reste strictement public et prioritaire.
  En cas d'échec de l'import riche, repli vers le catalogue public sans
  accorder d'identité OWNER.
- [x] Trois nouveaux tests Node de contrat valident le lien HTML, l'unique
  import statique et l'absence d'observateurs dans l'amorçage public.
  Le test HTTP d'assets vérifie la présence du nouvel entrypoint.
- [ ] **Exécuter les nouveaux tests** et prouver avec Chromium (ou Chrome
  DevTools) que la page publique ne charge pas `api-health.js` et qu'elle
  demeure interactive même avec un catalogue lent. Vérifier le parcours
  OWNER avec `ui_full=1`, les ACL et le rendu des sondes.
- [ ] **Déploiement ultérieur contrôlé** uniquement après revue et
  validation navigateur. Aucune CI GitHub, aucun déploiement automatique.

## P0 — Vérification du navigateur, catalogue public et Cloud 403 (28 octobre 2026)

- [x] **PR #381 testée localement sur TrueNAS au SHA 72b97623 :** 4/4 tests Node
  PASS en worktree détaché. La recette a rendu test_status=1 uniquement parce que
  l'ancien \`--preflight\` passait par mise/uv, a échoué en phase \`spawn\`,
  et n'a produit aucun rapport Python. Chromium n'a pas été testé.
- [x] **Preuves HTTP opérateur :** TrueNAS /api HTTP 200 (3 ms),
  /api/ui/session 200 (2 ms), /api/ui/services timeout à 3 s.
  Cloud /api, /api/ui/session et /api/ui/services HTTP 403 depuis le
  client urllib anonyme. Ces résultats ne prouvent aucun gel JS ni panne
  généralisée : la protection Cloud peut dépendre de l'identité/client.
- [x] **Préflight Playwright autonome :** \`--preflight\` exécute maintenant
  python3 sans mise/uv, sans téléchargement et sans navigation ; la sortie
  distingue \`playwright_python_missing\`, \`chromium_binary_missing\` et
  \`browser_binary_ready\`. \`--native\` permet de lancer Chromium via le
  même Python natif si Playwright y est déjà installé ; les erreurs de
  lancement restent classées sans afficher stderr.
- [x] **Budget serveur public** : Backstage v2 plafonné à 1,5 s,
  instantané health-board plafonné à 0,7 s, puis catalogue embarqué et
  états UNKNOWN sur absence de preuve fraîche. Le client conserve
  son délai de 6,5 s. La sonde transport applique 7 s uniquement
  à /api/ui/services afin de ne plus confondre 3 s avec ce délai client.
- [ ] **Exécuter les nouveaux tests de la branche PR #381** : tests Node
  public-first, tests Pytest de préflight absent, budget public et transport.
  Aucun test GitHub Actions et aucun nouveau déploiement automatique.
- [ ] **Comparer avec navigateur effectivement lancé** : TrueNAS /api,
  ?ui_safe=1, ?ui_full=1 ; Cloud /api et ?ui_full=1 depuis un client
  autorisé. Vérifier l'absence de boucle DOM et les longues tâches.
- [ ] **Publication** : le confinement public-first #381 reste uniquement
  dans une PR Draft ; pas encore déployé ni sur Cloud ni sur TrueNAS.
  Restaurer les cartes avancées par défaut seulement après preuve Chromium.

## P0 — UI Cloud + TrueNAS bloquée malgré #379 (27 octobre 2026)

**Preuves réelles avant nouveau correctif :** depuis la workstation,
la sonde HTTP a mesuré `truenas: /api=200 (4 ms), /api/ui/session=200
(2 ms), /api/ui/services=200 (766 ms)`. Chromium Playwright
`truenas` et `cloud` ont chargé `/api` et ses scripts avec HTTP
200, sans `pageerror`, mais `page.evaluate()` a expiré sur **les
deux** avec `main_thread_unresponsive`. Les 403 de la sonde Python
`cloud`/`staging` sont spécifiques à cet accès HTTP anonyme ; le
navigateur Chromium a obtenu HTTP 200 sur `cloud`. Ne pas confondre
règle Edge et disponibilité API.

**Déploiement TrueNAS maintenant terminé (27/10) :**
`update-fastapi-sample.sh` a construit puis redéployé
`fa13c08db05ce8ce086d2366e1f35706913f05be`
(hotfix #379), et atteint **`6/6 · final acceptance`** :
`health=4/4`, `observer=passed`, `Prometheus/Gatus=ok`,
`pfSense RBAC=warning` (diagnostic facultatif).
La version applicative 1.25.0 ne publie toujours pas son SHA via
`/v2/version` (`build_revision=null`) : la preuve de révision
est issue du journal de construction/déploiement, non de l'API.
**La sonde Chromium a été exécutée APRÈS cette recette** et
reste `main_thread_unresponsive` sur TrueNAS et Cloud.
Le correctif #379 seul n'a donc pas résolu le gel.

- [x] **Nouvelle boucle démontrée dans master après #379 :**
  `api-global-service-filter.js` appelle `mapTrueNasStatus()`
  sur un événement de son `MutationObserver` sur
  `#health-board` avec `attributeFilter: ["data-semantic-status",
  "hidden"]`, puis assigne inconditionnellement
  `panel.dataset.semanticStatus`. Même si la valeur ne change
  pas, le DOM émet une mutation, qui programme un autre rAF.
- [x] **Correctif #380** : appliquer
  `setDatasetValueIfChanged(panel, name, value)` à tous
  les attributs de présentation du panneau TrueNAS, dont
  `semanticStatus`, pour rendre les cycles idempotents.
- [x] **Tests locaux** : Node 22, **3/3 PASS**, dont 1000
  passes de statut identique et 500 passes de métadonnées.
  Empreintes Git identiques aux fichiers publiés.
  Chromium réel sur un panneau `#health-board` synthétique :
  deux affectations identiques sans garde provoquent 2 mutations ;
  100 passages avec garde provoquent une seule mutation initiale.
- [ ] **E2E production/staging après fusion #380** : le navigateur
  doit produire `sampled` avec frames/long tasks bornées,
  des filtres cliquables et un tableau lisible. Le test Chromium
  synthétique ne remplace pas l'E2E sur la page complète.
- [x] **Recette TrueNAS #379** : `fa13c08d` déployé avec
  `6/6` terminé et HTTP healthy ; l'interface est pourtant encore
  figée au test Playwright. pfSense RBAC reste `warning`
  indépendamment du chargement de /api.
- [x] **Contournement public-only #380** : `?ui_safe=1`
  ne démarre aucun contrôle opérateur, aucun collecteur de sondes
  ni observateur de cartes ; il utilise seulement
  `/api/ui/services` (deadline 6,5 s), sans escalade d'accès.
- [ ] **Comparer normal/safe après #380** :
  `node scripts/diagnose-production-api-ui-freeze.mjs truenas`,
  puis `node scripts/diagnose-production-api-ui-freeze.mjs truenas --safe`.
  Si seul le second termine `sampled`, isoler les modules
  UI avancés avant de les réactiver.
- [ ] **Tester le correctif #380** : déployer son commit
  immuable uniquement après la revue et sans autre déploiement
  actif ; confirmer l'absence de boucle avec Chromium.

## P0 — Hotfix gel /api malgré PR #378 fusionnée (26 octobre 2026)

**Preuve opérateur** : racine Cloud `/` utilisable ; page `/api` figée
après fusion de #378 (`f10c8147`, 22:43 CET). Les anciennes bornes
HTTP n'empêchent pas un cycle `MutationObserver` → rAF → mutation DOM.

- [x] **Cause de code à forte confiance** : la finalisation des cartes
  déplace chaque badge via `appendChild` à chaque frame, tandis que
  l'observer surveille `childList`. Le filtre global réécrit
  `innerHTML` des compteurs sans vérifier les valeurs, déclenchant
  sa propre observation. Le libellé pfSense pouvait aussi être réécrit
  sans changement.
- [x] **Correctif dans la nouvelle PR** : rendre l'ordre des badges
  idempotent ; ne reconstruire compteurs et filtres qu'au changement
  de signature ; ne pas réécrire les textes/classes déjà corrects.
- [x] **Tests ciblés locaux** : 7 tests Node.js passent sur des blobs
  identiques aux fichiers GitHub, avec 100 passes sans nouvelle mutation.
  Aucun GitHub Actions consommé.
- [x] **Logs plateforme reçus (26/10)** : `/api` répond HTTP 200
  en 6 ms, mais `/api/site/health/v2` retourne HTTP 500 avec
  `TypeError: not all arguments converted during string formatting`.
  L'origine est l'appel positionnel `logger.info("site_health_v2 trace_id={}", trace_id)`.
  L'opérateur a récupéré les logs avec le CLI `mise exec -- uv run
  fastapi cloud logs` ; aucun accès API Cloud supplémentaire requis.
- [x] **Correctif backend PR #379** : journalisation structurée
  `logger.info("site_health_v2", trace_id=trace_id)`, et test HTTP
  authentifié avec `traceparent` valide pour empêcher la régression 500.
- [x] **Dépendance Playwright locale** : le worktree PR #379 existe.
  L'échec `ERR_MODULE_NOT_FOUND: playwright` venait de l'import JS
  d'un package absent du `package.json` ; wrapper Node actualisé
  pour utiliser Playwright Python par `mise exec -- uv run --with
  playwright`, sans installation npm globale. Le diagnostic complet
  après mise à jour reste **NOT_RUN**.
- [ ] **Vérification runtime après déploiement** : `/api/site/health/v2`
  avec identité valide + traceparent doit répondre sans 500 ;
  `/api` doit rester interactif, sans boucle MutationObserver.
- [x] **TrueNAS staging réexécuté** : déploiement `origin/master`
  `f10c8147` (sans #379) ; health HTTP 4/4, Prometheus API 200,
  LiteLLM/Ollama/OpenRAG backend HTTP 200 ; la page
  `https://sample.albandrieu.com/api` reste pourtant bloquée
  sur Loading. Ne plus attribuer la panne à l'échec des sondes LAN
  sans preuve du navigateur.
- [x] **Playwright diagnostique corrigé** : Chromium installé sur
  workstation, mais l'ancien `spawnSync` de 50 s expire.
  Diagnostic Python **asynchrone** avec `page.evaluate` limitée
  à 2 s, phases de navigation, arrêt global à 35 s.
  Le lanceur accepte `cloud`, `staging` et `truenas`.
- [x] **Triage HTTP indépendant du navigateur** :
  `scripts/diagnose-api-ui-transport.py` relève trois endpoints
  essentiels par cible, timeouts 3 s, sans cookies ni données privées.
- [ ] **Mesurer hors Cloudflare Access** : sur workstation
  `node scripts/diagnose-production-api-ui-freeze.mjs truenas`
  et `python3 scripts/diagnose-api-ui-transport.py --target truenas`.
  Comparer `cloud`; pour `staging`, un 403/302 d'Access est
  une limite du navigateur automatique non authentifié.
- [ ] **Tester la vraie image #379** : master `f10c8147`
  ne contient pas le hotfix ; recette TrueNAS avec le HEAD immuable
  de #379 seulement après validation locale (sans toucher aux
  secrets du corpus Bababou).
- [ ] **UI en production** : fusionner/déployer le hotfix ;
  profiler la page Chrome Performance avant/après, relever
  long tasks et confirmer aucune animation infinie.
- [ ] **Résilience en panne TrueNAS** : maintenir l'inventaire public,
  les statuts non prouvés `UNKNOWN` et la réactivité des filtres.
  Ne pas redémarrer TrueNAS pour résoudre une boucle navigateur.

[Runbook incident Cloud /api](runbooks/fastapi-cloud-api-ui-freeze-20261026.md).

## P0 — Gel Cloud /api pendant une saturation mémoire TrueNAS (26 octobre 2026)

**Signal opérateur :** la page Cloud
`https://fastapi-sample.fastapicloud.dev/api` affiche `Loading` puis
semble figée ; TrueNAS a sa mémoire saturée. La panne LAN peut expliquer
les sondes indisponibles, mais le catalogue Cloud **ne doit jamais dépendre
de la terminaison de ces sondes pour afficher le repli public**.
Aucune disponibilité production n'a pu être mesurée depuis le runner
(cette session ne résout pas le DNS `fastapi-sample.fastapicloud.dev`).
**Cause exacte runtime NON CONFIRMÉE**, défauts de résilience identifiés
dans les sources JS.

- [x] **Code PR #378 :** borne de `4,5 s` sur
  `/api/ui/session` avant fallback public anonyme ; accès OWNER jamais
  accordé implicitement.
- [x] **Code PR #378 :** requête de répertoire public `/api/ui/services`
  bornée à `6,5 s`, y compris décodage JSON ; état d'indisponibilité
  explicite et anciens verdicts marqués `UNKNOWN`.
- [x] **Code PR #378 :** sondes `/api/health-board` bornées à
  `6 s` par requête et un seul retry `pending` (au lieu de 30) ;
  leur refresh reste serveur et asynchrone.
- [x] **Code PR #378 :** le panneau public sert de repli aux visiteurs
  readonly pendant que le tableau détaillé attend les sondes ;
  il disparaît après un événement de snapshot réussi.
- [x] **Code PR #378 :** ne pas démarrer immédiatement les flux LAN
  techniques fermés ; calcul des âges toutes les 10 secondes, sans
  rescanner toutes les cartes HTTP chaque seconde.
- [x] **Test local ciblé :** `node --test tests/js/api-request-deadline.test.mjs`
  → **4 PASS** sur les blobs Git exacts du helper et des tests.
- [ ] **Validation PR :** lancer `python -m pytest -q
  tests/unit/test_cloud_ui_outage_resilience.py` et les contrats UI,
  puis valider la page dans navigateur desktop/mobile sous
  DNS accessible et les trois scénarios : `session` bloquée,
  `ui/services` lent, `health-board` perpétuellement `pending`.
- [ ] **Production :** fusion/déploiement de #378, suivi des timings
  `/api/ui/session`, `/api/ui/services` et `/api/health-board` ;
  vérifier un inventaire public présent et des sondes dégradées
  affichées comme `UNKNOWN` pendant une panne TrueNAS.
  **Aucun déploiement déclenché ici.**
- [ ] **Infrastructure (nabla-compose) :** analyser la saturation TrueNAS
  (RAM, swap, pression ZFS ARC, OOM, mémoire des conteneurs) après
  stabilisation de l'accès ; pas de reboot déclenché par la page Cloud.

## P0 — Garage S3 : clarifier l'HTTP et la politique réseau

- [x] Rendre consultables les URL de catalogue internes et DNS via la
  fiche par ID stable, sans confondre S3, Admin et WebUI.
- [x] Déplacer le bouton Details sous la carte et afficher la cause
  `/sickz` du verdict Policy failed, même en cas de HTTP anonyme
  non pertinent.
- [ ] Vérifier sur TrueNAS un accès S3 **signé**, un bucket de test
  autorisé et les règles Traefik/Cloudflare de `s3.int.albandrieu.com`.
  Ne pas changer `external=false` sans validation réseau.

[Runbook Garage](runbooks/garage-s3-api-diagnostics.md).

## P0 — Provenance des erreurs et accès par route

[Contrat de diagnostic canonique](diagnostic-provenance-contract.md).
- [x] Classifier les échecs Backstage v2 sans exception ni secret dans la réponse
  (`upstream_timeout`, `upstream_network`, `upstream_http`,
  `upstream_auth`, `catalog_validation`).
- [x] Ajouter le code de phase `X-Nabla-Diagnostic-Stage` aux 503 du
  catalogue machine et tester les classes de panne.
- [ ] Contrôler sur la branche complète pytest/Ruff et les refus
  SERVICE/OWNER avec un JWT expiré, une source IP non autorisée et des
  en-têtes IP falsifiés.
- [ ] Propager un identifiant de trace unique depuis l'observateur jusqu'au
  Site ; ne pas confondre les IDs indépendants générés par Next.js.
- [ ] Inventorier toutes les routes HTTP/MCP/WebSocket/métriques et retirer
  progressivement la dérogation de lecture temporaire avec recette négative.
- [ ] Prévoir OIDC Keycloak / APISIX sans dépendre de leur disponibilité
  pour le contrôle applicatif immédiat.

### Dispatch d'architecture : livrables FastAPI de l'ADR-0001

**Propriétaire du contrat producteur :** `fastapi-sample`.
**Décision transverse :** [Compose ADR-0001 (proposed)](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/adr/0001-apisix-api-gateway-poc.md).
**Runbook :** [diagnostic de provenance](diagnostic-provenance-contract.md).
ADR-0001 est **accepted pour un POC APISIX staging** dans Compose #278 ; APISIX n'est ni déployé ni requis par FastAPI en production. L'agent peut avancer sans comité d'approbation pour les changements réversibles.

- [ ] **P0 Inventaire fail-closed** : comparer `server_all:app.routes`
  (HTTP, méthodes, mounts, WebSocket, MCP, docs, metrics) à `route_policy_for`.
  Produire la liste des routes `REVIEW` et décisions explicites par méthode.
  Ne pas activer `OPS_ROUTE_POLICY_STRICT` tant que ces refus n'ont pas été testés.
- [ ] **P0 Matrice d'autorisation** : tester `PUBLIC`, `SERVICE`,
  `OWNER`, `INTERNAL` sous accès LAN autorisé, IP non fiable, Access JWT valide,
  expiré/mauvaise audience et origine Cloudflare inaccessible. Chaque cas doit
  fournir statut et absence de données sensibles ; 302 d'edge n'est pas une santé API.
- [ ] **P0 Contrat erreurs v2** : conserver les codes fermés
  `catalog_validation`, `upstream_auth`, `upstream_http`,
  `upstream_timeout`, `upstream_network` ; tester le 503 de l'origine et
  les clés absentes. Aucun contenu d'exception brut ou URL interne.
- [ ] **P1 Trace distribuée** : définir source de `traceparent` fiable,
  propagation vers le site Vercel et les collecteurs, IDs de requête, limites
  de cardinalité/logging, scrubbing Sentry/OTel et politique de rétention.
  Tests croisés requis avec [Site #256](https://github.com/AlbanAndrieu/nabla-site-alban/pull/256).
- [ ] **P1 Contract testing gateway** : en staging seulement, préparer les
  réponses 200, 401, 403, 429, 502, timeout et `no-store` sous APISIX
  éventuel ; préserver les mêmes refus en accès direct FastAPI.
  Déploiement/APISIX/YAML/TLS/DNS/rollback restent **Compose #278**.
- [ ] **P1 Qualité** : lancer localement pytest/Ruff/quality sur HEAD exact,
  enregistrer `PASS` ou `NOT_RUN` par commande et ne pas confondre
  merge, déploiement Cloud et disponibilité de TrueNAS.

**Done FastAPI :** contrat versionné, routes inconnues explicitement
interdites selon politique approuvée, traçabilité vérifiée, aucun élargissement
involontaire des permissions, preuve négative et rollback du plan de migration.


## P0 — Conformité d'exposition outside-in sur les cartes

- [x] Afficher **Exposure** sur la carte principale sans déplacer ni
  supprimer `/sickz`. Un seul badge `policy` distingue disponibilité
  du service et conformité d'exposition.
- [x] Afficher `Private OK`, `Exposure !`, `Protected`,
  `Direct · Risk` ou `Exposure ?` avec provenance et fail-closed
  sur les observations absentes, sautées ou périmées.
- [x] Ajouter le filtre Exposure security policy et son explication dans
  le drawer avec lien vers les preuves `/sickz`.
- [x] Vérifier les ID canoniques du catalogue pour éviter les
  confusions entre services hébergés sur le même TrueNAS.
- [ ] Valider le rendu des badges dans la production au SHA réellement
  déployé avec un compte autorisé, en particulier la visibilité de la
  section `/sickz` et le rendu mobile.
- [ ] Comparer les violations indiquées par FastAPI avec le catalogue
  déclaratif Compose et les ingress/NAT réels sans élargir le périmètre
  des sondes externes.

**Contrat détaillé :**
[modèle de diagnostic et Exposure](platform-service-diagnostics-model.md).

### Validation rapide sans CI — Node 22/npm 10

- [x] Ajouter `just node22-quick` : contrats JavaScript autonomes, sans installation npm et sans GitHub Actions.
- [ ] Exécuter les deux suites avec **Node 22** sur un checkout complet au SHA de la PR. Le checkout Git n'est pas accessible depuis cet environnement (DNS GitHub indisponible). **NOT_RUN**, jamais PASS implicite.
- [x] Compiler sept modules et exécuter les contrats métier JavaScript via V8 isolé dans l'outil GitHub : **10/10 PASS** (ne remplace ni `node --test`, ni pytest, ni un navigateur).
- [ ] Conserver le contrôle complet séparé avec Node >=24.22.1, requis par `package.json`; ne pas abaisser cette contrainte pour permettre un test isolé.

### UX et convergence Gatus — critères d'acceptation

- [x] Dans chaque drawer, regrouper les éléments par DNS, TCP/TLS, HTTP, Cloudflare Access/token, Prometheus/exporter et Gatus ; afficher verdict, diagnostic expurgé et remédiation. La date de snapshot est affichée quand disponible. Les horodatages par sonde et leur origine exacte restent à enrichir côté DTO.
- [x] Ajouter URL partageable `?service=<id>`, filtre des échecs, focus clavier, retour entre dépendances et affichage mobile compact.
- [ ] Afficher les relations amont/aval avec lien uniquement si l'ID canonique existe dans le snapshot autorisé ; signaler les dépendances absentes sans URL réseau privée.
- [x] Réconcilier les échantillons Gatus avec les services visibles du catalogue (avec/sans métriques) sans faux statut vert.
- [x] Ajouter `scripts/reconcile-gatus-coverage.py` : contrôle **hors ligne** des 85 monitors déclarés dans Compose (63 TCP, 21 HTTP, 1 HTTPS), classés UP / DOWN / NO_SAMPLE / UNVERIFIED à partir d'un snapshot FastAPI autorisé ; collision de labels non considérée saine. **9/9 tests Python locaux PASS**.
- [ ] Vérifier la parité réelle de la configuration Gatus **en cours d'exécution** et des mesures LAN fraîches, avec validation du point d'observation et des endpoints. Les monitors absents du fichier ne peuvent pas être attribués automatiquement à une désactivation volontaire. Ne jamais déduire que toutes les sondes sont vertes de `up{job="gatus"} == 1`.
- [ ] Sur Gatus non sain, distinguer HTTP 401/403/token, erreurs DNS, timeout TCP, attente TLS, nom d'endpoint incohérent, absence de recording rules et manque de scrape Prometheus ; valider avec les preuves LAN de Compose, sans afficher de secrets.

## P0 — UX des cartes et couverture Gatus (25 octobre 2026)

- [x] Réutiliser le panneau `Details` déjà installé sur les cartes
  et la navigation entre dépendances/dépendants via les références
  uniques du catalogue. Le lien vers une autre carte doit ouvrir
  ses diagnostics, **pas** une URL extérieure supposée.
- [x] Grouper les vérifications Gatus en échec, réussies et sans
  échantillon utilisable dans le panneau Gatus. Les listes sont
  bornées ; un check absent reste **inconnu**.
- [ ] Afficher un résumé repliable par famille :
  transport DNS/TCP/HTTP/TLS, autorisation et token Cloudflare Access,
  Prometheus/scrape, Gatus et état fonctionnel. Mettre les échecs
  et données périmées en tête, avec heure/âge et source.
- [ ] Associer à chaque échec une explication stable et expurgée
  (ex. HTTP 401 token absent, HTTP 403 Access, timeout DNS,
  exporter UP mais `pg_up=0`) et un contrôle opérateur associé.
- [ ] Contrôler la **couverture complète** Gatus ↔ catalogue sur les IDs
  canoniques : `declared / observed / no_sample / missing_monitor /
  intentionally_unmonitored`. Gatus UP ne rend pas ses 85+ probes UP.
  Il faut comparer la définition des checks, les cibles, l'authentification,
  le point d'observation LAN, les états transitoires et les règles
  de mapping ; ne jamais forcer les voyants au vert.
- [ ] Tester l'accessibilité clavier et mobile du drawer (focalisation,
  taille tactile, listes scrollables, navigation entre cartes,
  statut accessible sans couleur) et la régénération des cartes
  après actualisation du snapshot.

**Limite de preuve :** l'accès direct à
`https://fastapi-sample.fastapicloud.dev/api` a été refusé dans
l'environnement de l'agent. Les nouveaux affichages ont été
committés mais **pas validés visuellement en production**.

## P0 — Authentification et collecte des métriques

- [x] Prometheus Inlet/Outlet Akvorado, Gatus et autres exporters
  déjà réconciliés par le code FastAPI avec des jobs nommés et une
  requête bornée ; un scrape ne prouve pas NetFlow → Kafka → ClickHouse.
- [ ] Valider en local la [PR #376](https://github.com/AlbanAndrieu/fastapi-sample/pull/376) :
  `METRICS_SCRAPE_KEY` limité à `GET/HEAD /metrics`, refus des autres
  routes, refus sans clé et tests de transport.
- [ ] Faire provisionner puis déployer cette clé sur le collecteur
  FastAPI staging **avant** d'ajouter le fichier d'authentification
  Prometheus dans Compose. Ne jamais rendre `/metrics` public.
- [ ] Diagnostiquer le **HTTP 403** de `/api/health-board` depuis la
  workstation : access denied = **projection cloud inconnue**.
  Vérifier Cloudflare Access, JWT/session, `DIAGNOSTICS_ACCESS_KEY`,
  source IP de confiance et SHA déployé ; ne pas désactiver les contrôles.
- [ ] Comparer après déploiement les scrapes LAN et le DTO
  `platform_metrics.exporter_jobs` de FastAPI Cloud. Conserver
  les provenances `lan` et `cloud` distinctes.

**Procédure unique :**
[acceptation télémétrie et accès Cloud](runbooks/fastapi-observability-acceptance.md).

## P0 — Qualité et sécurité du tableau de bord

- [ ] Vérifier les statuts `observed`, `disabled`, `not_configured`,
  `stale`, `failed` et `unverified`, pour HTTP/TCP/TLS/DNS,
  sans confondre l'état docker avec la réussite d'une sonde.
- [ ] Séparer cartes opérationnelles et graphe de dépendances.
  Rendre l'état Prometheus/Gatus sur les cartes Cloud **sans**
  inventer de sonde LAN depuis le runtime cloud.
- [ ] Vérifier le modèle `OWNER/SERVICE` : IP/URI internes,
  secrets, labels Prometheus et réponses privées ne doivent
  pas traverser le DTO public.
- [ ] Valider l'alignement catalogue `entityRef` Compose → FastAPI
  → Site, la couverture, la fraîcheur et les cas d'absence d'évidence.

**Référence** : [modèle des diagnostics](platform-service-diagnostics-model.md)
et [règles de sécurité](homelab-security-roadmap.md).

## P0 — Cartes de service et sondes Gatus

- [x] Enrichir le tiroir `Details` existant : verdict explicite
  `UP/FAILED/WARNING/UNVERIFIED/NOT RUN`, détails DNS/HTTP/TLS/Access,
  token et Prometheus issus des **preuves déjà rendues**, sans sondes
  supplémentaires par carte.
- [x] Lier les références upstream/downstream aux cartes du catalogue
  **par identifiant de nœud publié** ; ne pas inventer d'URL réseau pour
  des dépendances non exposées. Le lien navigue dans le tiroir.
- [x] Gatus : calculer depuis le snapshot Prometheus borné les checks
  `UP/DOWN/unknown`, afficher le compte de sondes rouges sur la carte
  Gatus et la liste cliquable dans le tiroir. Jamais de verdict « toutes
  vertes » sans parité avec le catalogue Gatus.
- [ ] Accepter sur une Preview au **SHA exact** les états token 401/403,
  erreurs DNS/TCP, métriques absentes et dépendances multiples.
  L'URL production n'était pas accessible depuis l'agent ; résultat
  live **NOT_RUN**.
- [ ] Après export du snapshot LAN (owner Compose), exécuter `just gatus-compare` sur la configuration réellement déployée et les `nabla_service_id` observés ; les définitions du dépôt ne prouvent pas l'état runtime. Procédure : [runbook Gatus](runbooks/fastapi-observability-acceptance.md).
- [x] Filtre échecs/avertissements, URL partageable
  `?service=<id>`, navigation retour, durée et disponibilité 5m
  sur mesures Gatus fraîches et bornées.
- [ ] Ajouter les historiques temporels Prometheus à plusieurs points, sans conclure à une disponibilité globale si des intervalles sont absents.

## P1 — Refactoring orienté domaine

- [ ] **`nabla/api/platform_metrics.py`** : séparer contrat des métriques
  et mapping de séries, agrégation et lecture HTTP. Conserver
  la requête PromQL fixe, le parsing fini et la cardinalité bornée.
- [ ] **`nabla/api/health_routes.py`** : extraire groupes de routes
  en modules versionnés sans modifier les URL/méthodes publiques.
  Ajouter tests du schéma OpenAPI et politiques OWNER/SERVICE.
- [ ] **`nabla/api/assets/api-service-*.js`** : partager une projection
  d'évidence typée vers les cartes, en gardant le graphe comme contexte
  et pas comme seconde source de statut.
- [ ] **CLI diagnostics** : une sortie différencie explicitement
  vérification LAN et projection cloud, conserve les limites de taille,
  temps et redirection et n'affiche jamais les secrets.

## P1 — Tests, coût et traçabilité

- [ ] Tester hors réseau, puis sur un collector LAN approuvé, puis sur
  le SHA exact déployé. Un merge ne prouve pas la production.
- [ ] Conserver les limites de budget, cache, circuit-breaker et
  single-flight, notamment pour les requêtes pfSense.
- [ ] Qualifier Sentry/OTEL/Pyroscope, intégration LiteLLM et flux
  d'événements métier PostHog avec configuration désactivée par défaut.
- [ ] Faire converger la couverture SAST/SCA/DAST et les importations
  DefectDojo sans lancer de GitHub Actions payante.

## Règles d'acceptation

Un résultat exige source d'observation, horodatage, verdict et
critère de clôture. `HTTP 403` est **denied**, pas service down ;
`scrape UP` n'est pas un succès fonctionnel. `NOT_RUN` est distinct
de `PASS`.

Pour la présente PR, la **quality gate complète est volontairement
NOT_RUN** sur demande de l'opérateur. Aucun contrôle de sécurité du
dépôt n'est supprimé ni neutralisé.

## P1 — Statuts HTTP protégés et contrat de santé

- [x] Couleur **bleue** `info` pour 401/403 anonyme attendu sur Garage
  S3 `GET /` et LiteLLM `GET /health`, avec indication
  « Authentification requise (attendu) ». Ne jamais assimiler
  une réponse protégée à un HTTP 200 ou à une disponibilité LLM/S3.
- [x] Diagnostic Drawer : compter les états d'authentification attendus
  séparément des `fail`, `warn`, `unknown` et `not_run`, en
  conservant les verdicts d'exposition `/sickz` indépendants.
- [ ] Vérifier sur le déploiement au SHA exact que `healthz` et les
  sondes réseau présentent le code 401/403, l'URL et le contexte
  d'authentification ; ne pas appliquer l'exception à une requête signée.
- [ ] Couverture étendue : établir depuis la source de vérité
  `nabla-compose` les contrats de santé de tous les services :
  `Docker HEALTHCHECK`, `Gatus TCP/HTTP`, routes de readiness et
  opérations fonctionnelles distinctes. Une absence de healthcheck
  reste `unverified` ; aucun sondage authentifié générique.
- [ ] Auditer Garage S3 `external=false` vs router Traefik
  `websecure` déclaré dans Compose ; exiger une vraie preuve
  outside-in avant de conclure à une exposition publique.
  Runbook : [Compose #281](https://github.com/AlbanAndrieu/nabla-compose/pull/281).


## P0 — Mise en page des cartes et diagnostic TrueNAS à distance

- [x] Réserver une zone pour **Details** en bas à droite des cartes de
  `/api`. Le badge d'âge des sondes reste en haut à droite.
  Préserver l'accès clavier et une surface tactile d'au moins 44 px.
- [x] Ajouter `--ssh-target utilisateur@172.17.0.24` au diagnostic
  `/metrics`. Utiliser SSH strict, sans proxy HTTP, sans transport de
  secrets locaux et sans déploiement sur TrueNAS.
- [ ] Valider le rendu réel à `https://sample.albandrieu.com/api`
  au SHA déployé, sur desktop/mobile. Commit Git ≠ application déployée.
- [x] Valider le diagnostic SSH distant sur TrueNAS depuis la workstation :
  `ssh -G` confirme le port `9922` ; `--ssh-target` retourne un
  HTTP 401 **anonyme attendu**. Pas de jeton testé.
- [x] Identifier l'écart de contrat entre FastAPI et Compose :
  FastAPI exige `METRICS_SCRAPE_KEY` ; le job `fastapi_sample` du
  catalogue Compose ne déclare pas encore `authorization.credentials_file`.
  La configuration réellement chargée par Prometheus reste à confirmer.
- [ ] Provisionner et vérifier le **jeton dédié** FastAPI/Prometheus dans
  `nabla-compose` (source de vérité des secrets et du collecteur), puis
  obtenir `up{job="fastapi_sample"} == 1` sans exposer la valeur.
  `scrape_authorized=false` et `credentials_tested=false` restent
  `UNVERIFIED` et **ne doivent pas devenir verts** par défaut.
- [ ] Exécuter localement les tests complets CSS/JS et FastAPI dans un
  checkout intégral. Les contrôles de ce changement n'activent pas de
  GitHub Actions payante.

## P0 — Recherche privée Bababou via OpenRAG (26/10, LAN indisponible)

- [x] Vérifier dans les sources OpenRAG v0.7.1 le MCP `/mcp` avec
  `X-API-Key` et l'outil `openrag_search(filter_id)`. La version et
  l'authentification du conteneur effectivement lancé sont **NOT_RUN**.
- [x] Préparer `POST /private/ops/ai/bababou/search` : classification
  OWNER JWT, `OPENRAG_BABABOU_FILTER_ID` fixé côté serveur,
  `MCP_CLIENTS` restreint à `openrag-frontend:3000/mcp`,
  `openrag_search` uniquement, réponse bornée et chemins expurgés.
- [x] Empêcher l'ajout automatique des outils OpenRAG aux agents
  génériques `/run` lorsque le client MCP privé est provisionné.
  Ne pas activer `OPENRAG_GENERAL_MCP_TOOLS_ENABLED` pour Bababou.
- [x] Ajouter les tests de refus (absence de clé/filtre, mauvaise URL,
  mauvais transport, sortie trop large et erreur MCP). Aucun fichier privé
  nécessaire pour ces tests.
- [ ] Provisionner un jeton OpenRAG dédié et un filtre de connaissance
  **limité au corpus autorisé** dans `sample/.env.secrets`.
  Ne pas confondre clé MCP avec clé LiteLLM ou OWNER.
- [ ] Vérifier OWNER, réseau source, index privé, tool-list, retour avec
  citations/page et impossibilité de lire un autre corpus. **Bloqué
  jusqu'au retour de l'accès LAN**.
- [ ] Confirmer la route LiteLLM `fastapi-qwen` avec la clé virtuelle,
  les appels d'outils, le budget et l'upstream workstation ; vérifier
  Ollama TrueNAS :30068 seulement si modèle local disponible.
- [ ] Contrôler que Langfuse/LiteLLM/OpenRAG ne conservent aucun prompt
  ni chunk privé avant une éventuelle génération d'answer.
  Pas de redéploiement, d'indexation ni de fuite de PII depuis le cloud.

## P0 — Site v2 et scrape métrique (reprise PR #378)

- [x] Accuser réception du `traceparent` W3C valide via `X-Nabla-Trace-ID` sur `/api/site/health/v2`, sans divulguer d'en-tête arbitraire.
- [x] Retirer les routes machine `/api/site/health/v2` et `/api/site/catalog/v2` de la dérogation `HOMELAB_PUBLIC_DIAGNOSTICS_READONLY`. Conserver les refus anonymes même en mode lecture temporaire.
- [x] Ajouter le préflight local `scripts/truenas/diagnose-fastapi-metrics-auth.py --check`, vérifiant les codes HTTP et jamais les secrets.
- [x] La PR #376 a été fusionnée : `METRICS_SCRAPE_KEY` reste limitée à `GET/HEAD /metrics`, aucun accès anonyme.
- [ ] Vérifier le SHA réellement déployé et la correspondance du jeton dédié côté FastAPI avec `authorization.credentials_file` côté Prometheus, sans imprimer la clé ni changer Compose ici. Preuve opérateur : `fastapi_sample` scrape HTTP 401, **non résolu en runtime**.
- [ ] Vérifier la propagation de la trace Site→FastAPI avec jeton machine en staging, y compris refus 401/503 et absence de reflet sur requête anonyme. `NOT_RUN` live.
- [ ] Contrats du checkout complet : pytest, Ruff et smoke en runtime autorisé. `NOT_RUN` tant qu'aucune preuve n'existe.
