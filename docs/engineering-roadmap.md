# Roadmap consolidée — FastAPI Sample

**État : 29 octobre 2026 · source canonique active.** Les anciennes preuves et
tâches restent accessibles dans l'[archive du 29 octobre](archive/2026-10-29/engineering-roadmap-before-consolidation.md)
et l'[archive du 24 octobre](archive/2026-10-24/engineering-roadmap.md).
Ne jamais convertir une tâche réalisée dans le code en résultat **validé en production**.

**Responsabilités :** FastAPI possède le contrat d'API, la sécurité des routes,
les DTO, les sondes et l'interface `/api`. [nabla-compose](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap.md)
possède les secrets d'exécution, les déploiements TrueNAS, HAProxy/pfSense,
Prometheus, Gatus et les règles d'ingress. [Site Alban](https://github.com/AlbanAndrieu/nabla-site-alban)
possède les composants Next.js, leurs icônes et le cache du navigateur.

## Tableau de bord des décisions

| Domaine | Code / GitHub | Dernière preuve réelle | Prochaine condition de clôture |
| --- | --- | --- | --- |
| OWNER smartphone | [#382](https://github.com/AlbanAndrieu/fastapi-sample/pull/382) **Draft, fusionnable** : entrée HTML, bootstrap isolé, session revalidée | Wi-Fi : `/api/ui/session` → `authenticated=false, readOnlyDiagnostics=true` ; accès direct LAN `:8091/api` OK | Tests locaux Node, connexion OWNER HTTPS, puis sondes détaillées |
| UI publique | [#380](https://github.com/AlbanAndrieu/fastapi-sample/pull/380) et [#381](https://github.com/AlbanAndrieu/fastapi-sample/pull/381) **fusionnées** : anti-boucle, démarrage léger | Chromium avant déploiement #380 : `main_thread_unresponsive` sur Cloud et TrueNAS | Vérifier les SHA déployés et exécuter un navigateur réel sur les modes public et riche |
| Déploiement TrueNAS | [Compose #289](https://github.com/AlbanAndrieu/nabla-compose/pull/289) **fusionnée** : classifieur de build disponible | Dernier déploiement accepté : `fa13c08d` (6/6). Build `0266f20d` refusé à l'étape 3/6, ancien runtime préservé | Classer le journal privé puis obtenir 6/6 sur un SHA immuable récent |
| Gatus / sondes | Mapping et scripts de réconciliation présents ; 85 checks déclarés | `gatus_up=1`, 85 échantillons synthétiques lors de la dernière recette, pas 85 checks sains prouvés | Comparer runtime, sondes fraîches, noms canoniques et états UP/DOWN/NO_SAMPLE |
| Prometheus `fastapi_sample` | Protection `METRICS_SCRAPE_KEY` fusionnée ; collecte et configuration relèvent de Compose | Dernier scrape signalé HTTP 401 ; `/metrics` protégé | Preuve `up{job="fastapi_sample"} == 1` avec authentification, sans divulgation de secret |
| pfSense / exposition | Badges et classifications d'exposition codés | Smoke RBAC pfSense : avertissement ; accès HTTP 401/403 parfois normal | Vérifier politiques et états avec preuve depuis le bon point d'observation |

**Référentiel des états :** `CODED` = enregistré dans Git ; `TESTED` = test local exécuté sur un SHA précis ;
`DEPLOYED` = image et runtime identifiés ; `ACCEPTED` = preuve utilisateur/sonde sur le runtime.
Une PR fusionnée n'implique ni `DEPLOYED` ni `ACCEPTED`.

## P1 prioritaire — Accès OWNER mobile et parcours TrueNAS

- [x] **CODED [#382] :** lien `Owner access` dans HTML (disponible même sans chargement
  JS du tableau) ; `?operator=1` ouvre le panneau via un module léger ;
  `?ui_full=1` est l'opt-in séparé vers les modules riches. Le mode
  `?ui_safe=1` demeure public uniquement.
- [x] **CODED [#382] :** états `Owner authorized`, `Owner locked / read-only` et public ;
  revalidation de la session sur `online`, `pageshow`, `visibilitychange`.
  Ne pas enregistrer `DIAGNOSTICS_ACCESS_KEY` dans le navigateur.
- [x] **Contrôles statiques de sources :** 23/23 PASS durant la préparation de #382.
  Il ne s'agit pas de tests Node/Chromium ou d'une preuve de déploiement.
- [x] **CODED — recette consolidée :** `scripts/truenas/validate-fastapi-ui-acceptance.py`
  unifie Node/pytest, HTTP TrueNAS/HTTPS, classifieur Docker Compose #289,
  /metrics, diagnostic Compose et quatre modes Chromium (public, safe,
  operator, rich), bornés, avec réseau opt-in seulement. Procédure :
  [validation OWNER TrueNAS](runbooks/fastapi-truenas-owner-acceptance-20261029.md).
- [x] **TESTED — lanceur isolé :** 10/10 tests unittest PASS sur la copie
  locale des sources publiées, et py_compile PASS. Les tests Node/pytest
  sur le checkout complet demeurent **NOT_RUN**.
- [ ] **TESTED :** exécuter `node --test tests/js/api-public-fast-start.test.mjs tests/js/api-chromium-preflight-runner.test.mjs`
  et `pytest tests/unit/test_api_ui_assets.py` sur un checkout de #382.
  Sans CI GitHub, enregistrer les résultats exacts.
- [ ] **ACCEPTED (connexion) :** sur le smartphone en Wi-Fi, vérifier
  `/api` → lien OWNER, `/api?operator=1` → bouton `Unlock diagnostics`,
  puis POST de session avec la clé **dans le formulaire uniquement**.
  Le statut doit devenir `authenticated=true`.
- [ ] **ACCEPTED (ACL) :** distinguer 401 (clé), 403 `source_unverified`
  (source/proxy), 403 `origin_unverified` (origine) et 503 (configuration).
  Le LAN `172.17.0.0/24` et l'IP domicile publique sont deux sources possibles,
  selon le chemin ; configurer `HOMELAB_TRUSTED_PROXY_CIDRS` seulement pour
  des proxies intermédiaires réellement vérifiés. **Le Wi-Fi n'est pas une identité.**
- [ ] **ACCEPTED (détails) :** ouvrir volontairement `?operator=1&ui_full=1`,
  retrouver les cartes DNS/TCP/TLS/HTTP, Cloudflare Access, token,
  Prometheus/exporters, Gatus et `Details` TrueNAS ; vérifier l'absence de gel.
  Afficher les relations upstream/downstream uniquement pour les IDs canoniques
  du catalogue accessible, avec navigation au drawer correspondant.
- [ ] **ACCEPTED (a11y) :** écran mobile, clavier, focus du drawer, boutons tactiles,
  rafraîchissement et suppression de données obsolètes ; pas de faux voyant vert.

**Done P1 :** OWNER peut être déverrouillé depuis la page publique sur un réseau
approuvé, les détails utiles s'affichent sans gel et une source non autorisée
reste refusée. `readOnlyDiagnostics=true` ne devient jamais OWNER.

## P0 de publication — Build Docker et gel du navigateur

- [x] **Historique :** #379 a été déployée sur TrueNAS (6/6) mais
  Chromium restait `main_thread_unresponsive`. #380 corrige une mutation
  `data-semantic-status` répétée ; #381 protège le catalogue public en
  déchargeant le graphe d'imports ESM lourds. Ces PR sont **fusionnées**.
- [ ] **Classifier** en lecture seule le journal privé du build de
  `0266f20d` (chemin opérateur historique : `/tmp/tmp.ngofCbFlgw`)
  avec `scripts/truenas/classify-fastapi-build-failure.py --check --failure-shape --log ...`,
  depuis le checkout **nabla-compose**. Ne pas publier le journal brut.
  Sans résultat du classifieur, ne pas attribuer arbitrairement l'échec à
  Dockerfile, RAM, BuildKit, réseau, dépendances ou Docker Hub 429.
- [ ] **Corriger selon la classe observée** ; une seule tentative de build
  contrôlée, sans purge globale, sans réinstallation et sans contournement
  des contrôles Docker Hub. L'ancien runtime doit rester préservé sur échec.
- [ ] **Prouver le runtime :** SHA exact, image OCI/provenance et acceptation
  `6/6`. La version `1.25.0` seule ne prouve pas le SHA (`build_revision=null`).
- [ ] **E2E navigateur :** mesurer public, `?ui_safe=1`, `?operator=1`
  et `?operator=1&ui_full=1` sur TrueNAS ; comparer l'environnement Cloud
  depuis un client autorisé. `pageErrors=0` n'exclut pas un gel du thread.
- [x] **CODED :** extension des diagnostics Chromium `--operator`,
  `ownerPanelVisible`, `ownerUnlockVisible`, `richAssetLoaded` ;
  aucun cookie/secret n'est lu. L'E2E TrueNAS reste **NOT_RUN**.
- [ ] **Conserver l'état public** si le mode riche gèle encore :
  pas de chargement automatique des MutationObservers avant preuve réelle.

**Done P0 :** build reproductible, 6/6, mode public interactif,
authentification OWNER non bloquée et navigation Chromium `sampled`
sur la vue riche. **Aucun déploiement n'a été exécuté dans la PR #382.**

## P1 — Qualité des cartes, Gatus et exposition

- [x] **CODED :** tiroir `Details` avec verdict et preuves classées par
  transport, sécurité et métriques ; liens upstream/downstream fondés sur les
  identifiants canoniques, filtre erreurs et lien partageable `?service=<id>`.
  L'affichage et les liens restent à valider sur le SHA effectivement déployé.
- [x] **CODED :** réconciliation `UP / DOWN / NO_SAMPLE / UNVERIFIED`,
  états d'authentification attendus distincts des pannes et badges d'exposition
  `Private OK / Exposure ! / Protected / Direct Risk / Exposure ?`.
- [ ] **Runtime Gatus :** comparer les 85 sondes déclarées avec les mesures
  réelles et chaque service catalogué. Présenter `declared / observed /
  no_sample / missing_monitor / intentionally_unmonitored`. `gatus_up=1`
  prouve l'accessibilité du collecteur, pas la santé de toutes les sondes.
- [ ] **Diagnostics précis :** différencier 401/403 attendu, échec de jeton,
  DNS, TCP, TLS, HTTP, exporter indisponible et `pg_up=0`.
  Inclure timestamp/âge et provenance pour chaque preuve, sans exposer
  d'URI internes aux visiteurs publics.
- [ ] **Exposure outside-in :** vérifier Garage S3 signé et la politique
  `s3.int.albandrieu.com`, les ingress Cloudflare/HAProxy/Traefik, puis
  confronter `/sickz` au catalogue sans élargir l'exposition.
- [ ] **Prometheus :** attester l'autorisation du scrape dédié,
  puis rapprocher `platform_metrics.exporter_jobs` des séries LAN.
  `GET /metrics` anonyme doit rester 401 ; refus attendu ≠ service down.

**Done :** une carte affiche état, transport, preuve fraîche et remédiation ;
les relations sont navigables et aucune sonde absente n'est affichée en vert.

## P2 — Sécurité des contrats et interopérabilité

- [ ] Inventaire strict HTTP/ASGI/MCP/WebSocket/metrics et tests négatifs
  des rôles `PUBLIC / SERVICE / OWNER / INTERNAL` ; supprimer graduellement
  les dérogations de lecture temporaires après migration autorisée.
- [ ] Propager `traceparent` / `X-Nabla-Trace-ID` de Site Alban vers
  FastAPI et ses collecteurs, avec scrubbing et tests 401/403/503/timeout.
- [ ] Refactorer `platform_metrics.py` en contrat/lecture/agrégation,
  `health_routes.py` en modules versionnés et les composants
  `api-service-*.js` autour d'une projection de preuve unique.
- [ ] Qualifier LiteLLM / OpenRAG Bababou : clé et filtre privés dédiés,
  identité OWNER, corpus autorisé, absence de fuite, budget et traçabilité.
  Ne pas considérer HTTP 200 ou MCP 406 anonyme comme test métier.
- [ ] Tester APISIX uniquement en staging sous décision Compose ADR-0001,
  avec parité des réponses 200/401/403/429/502 et rollback ;
  aucune dépendance de production à ce POC.
- [ ] Compléter Sentry/OTel/Pyroscope, exposition des données, SAST/SCA/DAST
  et import DefectDojo en mode local-first, sans crédit GitHub Actions.

## Ordre de recette et règles de preuve

1. **Sur checkout FastAPI #382 :** lancer les contrats Node 22 puis
   les tests Python disponibles ; conserver le SHA précis et le verdict.
2. **Sur TrueNAS / Compose :** classifier le journal Docker en lecture seule.
   Ne pas coller de secret ni de log brut dans une PR.
3. **Déploiement contrôlé :** après résolution du build, déployer un SHA
   immuable de FastAPI et vérifier les six étapes, l'identité de l'image et
   la non-régression des sondes. Pas de redéploiement concurrent.
4. **Sur smartphone LAN :** vérifier `/api`, `?operator=1`, authentifier
   via formulaire, puis activer `ui_full=1`. Comparer les chemins HTTPS via
   proxy et HTTP LAN sans attribuer le même client IP aux deux.
5. **Après succès :** valider Gatus, Prometheus, pfSense, cartes et dépendances,
   puis clôturer seulement les items portant des preuves reproductibles.

Les preuves portent le triplet **version/SHA · point d'observation · heure**,
plus verdict et logs expurgés. `NOT_RUN` ≠ `PASS`; `HTTP 403`
signifie `denied`, pas `down`. `scrape UP` ne prouve pas la fonction métier.
Ne jamais ajouter d'ACL `0.0.0.0/0`, désactiver la vérification d'identité,
faire d'automerge ou relancer GitHub Actions pour cette recette.

**Runbooks :** [incident UI](runbooks/fastapi-cloud-api-ui-freeze-20261026.md) ·
[observabilité](runbooks/fastapi-observability-acceptance.md) ·
[provenance](diagnostic-provenance-contract.md) ·
[exposition et diagnostic](platform-service-diagnostics-model.md).
