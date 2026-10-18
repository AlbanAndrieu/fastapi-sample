# Engineering and security roadmap

## P1 — Campagnes distinctes et diagnostics local-first (PR #350, 2026-10-18)

- [x] **GitGuardian PR #350** — historique actif consolidé et occurrence historique de Basic Auth factice écartée des commits de la PR ; contrôle GitGuardian **SUCCESS** sur le commit consolidé, 1 commit analysé et aucun secret détecté. Branche antérieure conservée pour restauration, sans désactiver le scanner. Les autres contrôles GitHub Actions restent non exécutés sur les commits `[skip ci]` : aucune affirmation de CI globalement verte.
- [x] **Tâche de sonde annulée avant échéance** — intercepter explicitement `asyncio.CancelledError` d'un enfant déjà terminé, état `warn` / `probe_cancelled`, compteur `cancelled` séparé des observations `completed` et des expirations `timed_out`. Test asynchrone de non-régression ajouté ; exécution de la suite complète toujours en attente.


- [x] **Historique de la PR consolidé pour GitGuardian** — correctif de la fixture de test déjà appliqué ; conservation du contenu de la PR en un commit de synthèse bâti directement sur `master`, afin que l'ancienne occurrence synthétique Basic Auth ne fasse plus partie des commits analysés dans la PR. Sauvegarde de l'ancienne branche : `backup/pr350-before-gitguardian-squash-20261018`. Aucun désarmement de GitGuardian ; son résultat sur le nouveau commit reste à contrôler. Le SHA du commit historique problématique n'est pas reproduit dans cette roadmap.


- [x] **Éliminer les relectures du cache dans la comparaison** — `scripts/audit/summarize_homelab_cycles.py --aggregate` déduplique les observations `fresh/origin` par `homelab.checked_at`, et exclut les enveloppes dépourvues d'un identifiant temporel ISO UTC strictement validé. `health-board.generated_at` ne constitue **pas** une preuve d'une nouvelle campagne réseau. Compteurs de répétitions et de preuves manquantes, tests de non-régression et conservation du filtrage des secrets.
- [x] **Contrat d'acceptation hors réseau** — option `--require-three-origin-cycles` pour exiger trois campagnes distinctes (exit 3 sinon), tout en fournissant une synthèse JSON assainie. Aucun appel HTTP/DNS depuis l'agrégateur, aucun changement des budgets de sondage.
- [x] **Durcissement du comparateur de cycles (PR #350)** — rejeter les collections de services non-listes sans planter et dédupliquer les variantes UTC équivalentes (secondes fractionnaires) : trois lectures du même instant ne peuvent pas valider le seuil de trois campagnes. Fixture d'URL expurgée de toute syntaxe Basic Auth factice ; le signalement GitGuardian historique reste à réconcilier côté intégration. Tests de contrat ajoutés, exécution du HEAD exact restant nécessaire.
- [ ] **Validation locale du dernier HEAD** — les 30 tests ciblés étaient verts sur TrueNAS à `aa2491b5`; Ruff C420 a été corrigé dans `e887499d`, mais la gate et les nouveaux tests de déduplication devront être exécutés sur le commit courant avec `UV_PYTHON=/usr/bin/python3.13` et `TMPDIR` exécutable. Ne pas transférer la preuve de tests d'un ancien SHA.
- [x] **Preuve de publication locale explicite** — le wrapper TrueNAS accepte désormais `--publish` (tests ciblés → gate `--fix` → contrôle d'arbre propre → `agent-publish.sh`), conserve `UV_PYTHON=/usr/bin/python3.13`, `TMPDIR` exécutable et `UV_OFFLINE=1` sur demande. Aucun `push`, merge ou bypass de validation ; une correction formatter non commitée bloque la preuve avec code 3.
- [ ] **Acceptation runtime ultérieure** — seulement après validation locale et déploiement volontaire du SHA immuable, réunir au moins trois identifiants `homelab.checked_at` distincts via le script de synthèse et comparer `deadline_phase_counts` aux expirations. Aucun merge ni déploiement automatisés.

## P1 — Sondes Garage : preuve de phases et comparaison des cycles (PR #350)

- [x] **Présentation sans nouvelles requêtes** — exposer dans le panneau « Homelab probe fan-out » les phases déjà mesurées `queue_wait_ms`, `dns_probe_ms`, `http_request_ms`, `access_secondary_ms`, avec nombre de probes effectivement instrumentées et maximum par phase ; afficher `deadline (phase unknown)` quand l'échéance globale empêche la mesure, et ne jamais convertir `null` en 0 ms. Le budget 4 s, la concurrence 4 et l'échantillonnage 12 restent inchangés.
- [x] **Triangulation de plusieurs cycles sans réseau** — `scripts/audit/summarize_homelab_cycles.py --aggregate` accepte au plus 64 instantanés JSONL préexistants et émet une synthèse assainie : intervalles de probes publiques terminées/expirées, nombre de réponses stale, maxima des phases **terminées**, Garage LAN 3/3 et dérive Cloudflare Admin. Seuls les cycles de board `fresh` avec `probe_cache.source=origin` sont comptés pour la performance ; aucune réponse stale/cached n'est promue en nouvelle mesure.
- [x] **Acceptation partielle staging 1.22.2 sur SHA `0902a9a0`** — image reconstruite distincte du rollback, deux assets HTTP 200, les trois Garage visibles dans l'UI `/api?q=garage`, `/health=healthy`, Gatus/Prometheus présent et pfSense RBAC 7/7. Le health-board passe de `pending` à `fresh`, puis `stale` lors du prochain recalcul ; le log montre une construction de 6,673 s. La dérive Cloudflare Admin reste à prouver indépendamment.
- [x] **Observation explicite du fan-out variable** — deux vagues avec 2/12 puis 1/12 probes publiques achevées (maxima DNS 1 600 puis 1 102 ms) ; une vague distincte 12/12 en 3 073 ms (attente sémaphore max 1 779 ms, DNS 599 ms, HTTP 635 ms, Access 1 000 ms). Les maxima **ne proviennent pas nécessairement de la même probe** et les mesures d'une enveloppe `stale` ne sont pas des résultats à l'instant de lecture.
- [x] **Attribution à l'annulation** — enregistrement en mémoire des phases `waiting_on_semaphore`, `dns_in_progress`, `head_get_in_progress`, `access_secondary_in_progress` et `tcp_in_progress` (plus `not_started`) via un registre à clés de tâches faibles ; `deadline_phase_counts` et phase/temps partiel exposés sans URL ni identifiant. Capture **avant** `task.cancel()`, mémoire nettoyée après `asyncio.gather()` et preuves `memory` séparées du dernier essai expiré. Tests réseau simulé et contrat d'affichage ajoutés ; gate complète différée.
- [ ] **Acceptation du prochain SHA de PR** — après déploiement volontaire d'une version validée, comparer au moins trois vagues `probe_cache.source=origin` avec `deadline_phase_counts`, les phases des entrées `deadline` et les dernières tentatives sur preuves `memory`. Ne pas confondre cache, succès réseau et deadline. Ne pas augmenter budget 4 s, concurrence 4 ni échantillonnage 12.
- [ ] **Optimisation conditionnée aux mesures** — si l'attente sémaphore domine, examiner la contention commune LAN/public et la durée de retenue ; si le DNS domine, examiner la résolution explicite A/AAAA et HTTPX. N'éliminer ou paralléliser aucune sonde ni phase de sécurité avant acceptation de la nouvelle attribution.
- [ ] **Contrôles finaux différés sur demande opérateur** — conserver les hooks EditorConfig, SAST/DAST et la gate de publication inchangés ; les exécuter avant fusion, pas pendant cette itération de développement.

## P1 — Catalogue de criticité et sondes par unité de déploiement (2026-10-17)

- [x] **Préparation hors ligne (sans activation runtime)** — `nabla/api/homelab_probe_units.py` lit des composants explicites `deploymentUnitId`, `probePriority`, `probePolicy`, expose un aperçu JSON sans appels réseau et conserve l'isolation des observateurs. 14 tests locaux de contrat réussis ; quality gate complète et `agent-publish.sh` verts le 2026-10-17 sur le checkout réel de #342 (après découpage de `build_probe_units` sous le seuil Ruff C901). Aucune migration de l'échantillonnage existant.
- [ ] **Acceptation avant raccordement runtime** — publier réellement le schéma canonique dans `nabla-compose` (PR #257 actuellement metadata staging), inclure la révision du catalogue et un modèle typé, puis comparer l'aperçu avec les consommateurs existants. Le budget de 12 reste en *unités sélectionnées* ; déterminer séparément le budget HTTP réel par composant, les conditions de sondage Admin et le verrou singleflight avant tout déploiement.
Reference: [nabla-compose PR #257](https://github.com/AlbanAndrieu/nabla-compose/pull/257), `docs/watchtower-service-units.md`. **Roadmap only**; do not imply the current probe runtime has already changed.

- [ ] Reconcile canonical `x-nabla` and its catalog-v2 revision with FastAPI package fallback, origin and live TrueNAS apps. Preserve the existing direct v2 cutover plan (no permanent v1/v2 shim).
- [ ] Distinguish `operationalCriticality` from BIA-derived `businessCriticality`; do not infer business criticality from display role or use a missing value as Low. Reuse catalog unit-level `stateful`, `upgradePolicy` and dependency metadata for *display/observation*, not an administrative Docker control plane.
- [ ] Add normalized `deploymentUnitId`, logical endpoint/member relations, `probePolicy` and ordered dependencies in the canonical catalog. The keys `garage` (S3 :3900), `garage-admin` (Admin :3903) and `garage-webui` (UI :3909) remain distinct but share `truenas:garage` for scheduling, caching and upgrade-policy grouping.
- [ ] Replace three parallel Garage fan-outs with a bounded, serialized, cache-aware **per-unit** probe sequence: primary read-only S3 probe, conditional Admin probe and WebUI probe, with shared cooldown, singleflight, capped concurrency and per-endpoint evidence/staleness. Use the dependency DAG for ordering; separate internal and outside-in observers. Never repeatedly hammer Admin API or Cloudflare Access.
- [ ] Preserve #342's **12-target sampling budget with 10 prioritized + 2 rotating slots**, rotating across units and independently tracking component coverage; prevent starvation even if selected units have multiple endpoints. A group counts as one scheduling selection, **not** a promise of unlimited probes.
- [ ] Preserve independent health vs exposure intent: `external=false` requires LAN validation and outside-in exposure audit; Cloudflare 302/403 does not prove origin health or exposure; stale/missing LAN evidence must not turn DOWN or GREEN without proof. Timeouts become warning/unknown, not speculative runtime DOWN.
- [ ] Add regression tests for Garage unit deduplication, priority order, no-starvation rotation, 1–3 target budgets, TTL and stale evidence, access-protected probes, and conservative degradation. Measure probes/minute, concurrency, latency and TrueNAS/pfSense CPU before/after. Avoid changing the production cloud's no-LAN-probe posture.
- [ ] Publish unit-level summary + per-component evidence and provenance on health-board only after local-first quality gate, synchronized catalog revisions and accepted rollback plan.

### P0 — Garage absent des cartes de `/api` (2026-10-17)

- [x] **Défaut de raccordement identifié** — les trois composants Garage apparaissent dans `/api/health-board.homelab.services` et `internal_services` après #342 ; pourtant `api-health-core.js` ne crée des cartes que pour `healthz.checks` et `mergeHomelabEvidence` enrichit uniquement ces contrôles existants. L'agent ne peut pas ouvrir la session Cloudflare Access de l'opérateur ; la disparition visible est son observation, la cause dans le code est vérifiée.
- [x] **Correctif UI protégé** — ajouter les trois Garage manquants sans doublons, garder `garage` (S3), `garage-admin` (API Admin), `garage-webui` (WebUI) distincts. Une preuve interne récente est distincte du contrôle d'exposition : Admin `internal` avec `unexpected_tunnel_route=true` demeure *At risk*. Seule la WebUI dispose d'un lien externe autorisé. Les résultats `stale`, sans LAN ou en deadline restent **UNKNOWN** et ne deviennent jamais verts.
- [x] **Filtres fondés sur le contrat** — déclarations `exposure_intent=internal/public` projetées vers le filtre d'exposition en complément des observations `sickz`, sans inférer `policy compliant` depuis `internal_state=ok`. Tests Node isolés et assertions de raccordement.
- [ ] **Publication locale** — exécuter les tests ciblés JS/Python, le formatage/EditorConfig et `agent-publish.sh` sur le nouveau HEAD propre ; pas de coût GitHub Actions induit par un `[skip ci]`.
- [ ] **Acceptation staging/navigateur** — seulement après un déploiement du nouveau SHA avec rollback : vérifier trois cartes, la recherche « garage », le filtre « At risk » pour Admin, « Internal-only » pour les API, et l'absence de lien public sur l'Admin et le S3. Le staging actuel `5fe39a33` n'embarque pas ce correctif.
- [ ] **Ancienne erreur quality gate dans worktree détaché** — le premier `uv run --no-sync pytest` a créé une `.venv` vide (`starlette` absent). La passe `--fix` a ensuite laissé quatre fichiers modifiés et `agent-publish.sh` les a refusés (comportement attendu). Une fixture imbriquée `test_agent_publication_proof` a aussi retourné exit 30 dans ce contexte ; conserver sa sortie complète pour attribuer ce cas si un HEAD propre le reproduit, sans neutraliser ce test. Le HEAD concurrent `2902b13b` dispose déjà d'une preuve workstation de quality gate verte, non transférable au futur commit UI.

## P1 — Garage : couverture des sondes LAN et reconciliation DNS (2026-10-13)

- [x] **Contrat d'audit offline renforcé** — preuves sourcées par couche et horodatées, expiration à 24 h par défaut, indéterminé pour un edge Cloudflare protégé, aucune conclusion d'accès anonyme à l'origine. 15 tests de réconciliation + 14 tests de planification d'unité réussis dans un environnement Python isolé, puis validation complète du dépôt avec dépendances verrouillées le 2026-10-17 (bit exécutable de `scripts/audit/garage_exposure_drift.py` restauré, `reconcile` découpé sous le seuil Ruff C901). Récidive : une écriture de fichier par API (e65aaddf) avait remis le mode à 100644 — préférer le checkout local.
- [x] Conserver `garage` (S3 API :3900), `garage-admin` (Admin API :3903) et `garage-webui` (Web UI :3909) dans l'échantillonnage prioritaire des sondes internes, même lorsque le catalogue dépasse le budget de 12 cibles par cycle. Ne pas activer les sondes LAN sur la production cloud.
- [x] Corriger la saturation des 12 places de priorité : réserver deux places à la rotation des services non prioritaires et aligner l'estimation de fréquence des sondes, y compris les cas de budget nul. Vérification par tests de non-famine ajoutés ; exécution locale en attente.
- [x] Vérifier dans le catalogue source que les deux API sont `external=false`, avec WebUI `external=true` temporairement ; maintenir des noms explicites sans réutiliser l'identifiant technique de l'API pour l'UI.
- [x] La couverture des preuves de sondes exclut maintenant les lignes `probe_stale=true` et les échéances sans observation : elles restent consultables mais ne sont plus comptées comme des preuves valides. Test de non-régression ajouté ; exécution locale encore requise.
- [x] Séparer la politique `internal` de l'état fonctionnel : une sonde LAN valide peut confirmer la santé d'une API privée, un ancien tunnel Cloudflare ne dégrade pas directement sa santé mais génère `unexpected_tunnel_route=true` (à auditer), et une preuve LAN périmée ne compte plus comme santé actuelle. Tests ajoutés, exécution encore requise.
- [x] **Acceptation Garage LAN TrueNAS + workstation (2026-10-17)** — les trois identités S3/Admin/WebUI sont visibles dans `homelab.internal_services` sur chacun des trois cycles du runtime TrueNAS `master` `5fe39a33`, avec `internal_state=ok`. Le cloud observer ne peut toujours pas prouver la santé LAN ; absence de sonde ≠ DOWN. Détails et preuves dans [l'acceptation staging](runbooks/garage-truenas-staging-acceptance-2026-10-17.md).
  - [x] **Workstation (2026-10-17, HEAD `484415aa`, LAN, `HOMELAB_INTERNAL_PROBES_ENABLED=true`)** — bloc `homelab` construit hors lifespan (PostgreSQL local absent), 3 cycles à 31 s : `garage`, `garage-admin`, `garage-webui` sondés en interne **à chaque cycle**, tous `internal_state=ok`, `probe_stale=false` ; rotation effective (couverture 14,0 → 17,4 → 20,9 %, aucune preuve périmée) ; `exposure_intent` = `internal` pour les deux API et `public` pour la WebUI ; `rotated_priority_ids=[]` (9 priorités seulement présentes dans le catalogue bootstrap). Limites : sans identifiants TrueNAS ni Cloudflare sur la workstation, `runtime_state` est nul et `unexpected_tunnel_route` ne peut pas être prouvé (0 tunnel observé).
  - [x] **TrueNAS staging (2026-10-17)** — `FASTAPI_SAMPLE_DEPLOY_MODE=build FASTAPI_SAMPLE_REF=master` a construit le HEAD mergé `5fe39a33c3b8c6bf86c3ab1b17384259e09e7af7`. App `RUNNING`, `/health=healthy`, pfSense RBAC 7/7, `garage`, `garage-admin` et `garage-webui` présents **3/3 cycles** avec `internal_state=ok`. `garage-admin` conserve `exposure_intent=internal` et `unexpected_tunnel_route=true` (dette P0 d'exposition indépendante de la santé LAN). `/v2/version.build_revision=null` ne prouve pas encore le SHA de l'image.
- [ ] **P0/P1 — Identifier l'origine des expirations publiques variables** — après déploiement #342 : `completed/timed_out=1/11,1/11,11/1` puis `11/1,1/11,12/0` avec le **même budget 4 s**, sans défaillance LAN Garage. Résolution DNS/TCP/TLS Python directe depuis le conteneur vers `garage.albandrieu.com` : **47/4/13 ms**, IP edge `188.114.97.2`. HTTP curl hôte/conteneur ~0,1–0,6 s ; les temps curl DNS/connect/TLS sont cumulatifs et ne prouvent pas une panne egress. Prioriser contention du sémaphore partagé interne/public, volume de requêtes HEAD/GET, éventuelles sondes secondaires Access hors sémaphore et cache/stale ; analyser les nouveaux `probe_summary.public.timing` et `public_probe_results[].probe_timing` en comparant `completed_samples` avec `timed_out`, sans relever le budget ni solliciter pfSense.
- [ ] **Cross-repo catalogue source et priorité** — les diagnostics TrueNAS 2026-10-17 constatent **une seule entrée LanguageTool locale** : l'ancien doublon ne doit plus être déclaré comme un incident actuel sans preuve sur le catalogue distant. Trois entrées Garage ont `probePriority=null`, `deploymentUnitId=null` et `priority_source=bootstrap`. Publier les métadonnées dans le catalogue autoritaire `nabla-compose` avec tests d'unicité/provenance puis confirmer `priority_source=catalog` ; aucune migration du fan-out vers les unités n'est activée dans cette PR.
- [x] Documenter le runbook `docs/runbooks/garage-public-ingress-audit.md`, y compris les commandes pour comparer catalogue, DNS public, Cloudflare Tunnel, HAProxy/NAT, Traefik et réponses outside-in sans divulguer les paramètres signés de Cloudflare Access.
- [ ] Auditer les origines actives Cloudflare Tunnel : `garage.albandrieu.com` a renvoyé du XML S3 ; le 2026-10-15, `garage-admin.albandrieu.com` renvoie `HTTP/2 302` vers le login Cloudflare Access. Cela confirme une route publique à l'edge, mais ne prouve pas l'accès anonyme à l'origine ni son port. Comparer les ports :3900/:3903/:3909, routes Access et contenu de réponse ; retirer l'ingress public Admin API après confirmation de sa source de configuration.
  - [x] **Relevé outside-in du 2026-10-17 (workstation LAN, `collect_outside_in_evidence.py`)** — `garage-admin.albandrieu.com` → edge Cloudflare (188.114.96/97.x), `HTTP 302` vers le login Access : route publique toujours active pour une API `external=false` ⇒ `requires_review`. `garage.albandrieu.com` (WebUI, `external=true`) → edge Cloudflare, `302` Access : cohérent ⇒ `no_confirmed_drift` (le XML S3 du 2026-10-15 n'est plus observé à l'edge). `s3.int.albandrieu.com` (S3 API, `external=false`) a un enregistrement **DNS public** vers l'IP WAN du homelab `82.66.4.247` (`_DEFAULT_HOMELAB_WAN_IPV4` ; la topologie déclare le frontend HAProxy public `fWeb_HTTPS` lié à cette IP sur :443), et Garage y répond `403 AccessDenied` « does not support anonymous access » ⇒ `requires_review`. Depuis le LAN cette requête passe par la NAT reflection pfSense : **ce n'est pas une preuve d'accessibilité WAN**.
  - [ ] Preuve d'acceptation : depuis un point de vue hors LAN (FastAPI Cloud ou réseau mobile), `curl -sS -o /dev/null -w '%{http_code}' https://s3.int.albandrieu.com/` ; si une réponse Garage arrive, la route HAProxy/NAT publique du S3 est réelle → la retirer ou la restreindre et supprimer l'enregistrement DNS public `s3.int` (côté `nabla-compose`/pfSense) ; retirer aussi la route tunnel publique `garage-admin`.
- [ ] Intégrer l'audit DNS public + HAProxy/NAT pfSense + Traefik + Cloudflare dans un rapport de drift `declared/observed/unknown`, avec preuves outside-in. La politique privée n'est pas une preuve d'inaccessibilité WAN.
  - [x] Couches `public_dns`, `cloudflare_access` et `outside_in_origin` collectées en lecture seule par `scripts/audit/collect_outside_in_evidence.py` (exclusion explicite de l'IP WAN en hairpin, résolution LAN = `unknown`, `Location` jamais conservé) ; un DNS public pour un service privé déclenche désormais `requires_review` dans `garage_exposure_drift.py` au lieu de `no_confirmed_drift`. Tests hors ligne.
  - [ ] Collecteurs `cloudflare_tunnel` (API Cloudflare, lecture seule), `pfsense_nat_haproxy` et `traefik` (configuration) : à écrire avec des identifiants en lecture seule hors Git, puis publier le rapport complet sur le health-board.
- [ ] Évaluer accès privé distant via Tailscale/WireGuard pour retirer à terme la WebUI de l'Internet public ; en attendant, conserver uniquement l'UI publiable derrière contrôle d'accès.
- [x] Exécuter localement les tests ciblés et la quality gate complète sur le checkout réel (2026-10-16, `agent-publish.sh` sur le HEAD de #342) ; ne pas consommer GitHub Actions pour une validation non nécessaire et ne pas merger automatiquement.
- [x] Budgets minuscules (`limit` 1 à 3) saturés par les priorités : l'estimation de fréquence renvoie `None` au lieu d'une division par zéro. Couvert par un test paramétré 1/2/3.
- [x] Remplacer le double ensemble en dur (`_PRIORITY_SERVICE_IDS` + `garage_ids`) par un ordre unique `_PRIORITY_SERVICE_ORDER` : quand les 12 priorités dépassent les 10 places fixes, les moins bien classées (`n8n`, `pyroscope`) passent en rotation de façon déterministe, indépendamment de l'ordre du catalogue, et sont exposées dans `homelab.{public,internal}.rotated_priority_ids`.
- [ ] **Cross-repo `nabla-compose`** — déclarer la priorité de sonde dans le catalogue au lieu du code : ajouter un champ optionnel `probePriority` (entier, rang croissant, absent = rotation) dans `catalog/homelab-exposure-overrides.json`, avec validation de schéma côté `nabla-compose`. Regrouper par composant via `sourcePath` (ex. `apps/garage/compose.yml` → `garage`, `garage-admin`, `garage-webui`) plutôt que par liste d'identifiants. Ne pas dériver la priorité de `criticality` : 30 nœuds `critical`/`high` dépassent le budget de 12.
- [x] **Catalogue `fastapi-sample` (côté consommateur, 2026-10-17)** — `HomelabService.probe_priority` (alias `probePriority`, entier strict 0–1000) est propagé par `_apply_exposure_overrides` et lu par `_probe_partitions`. Dès qu'**un** service du catalogue déclare un rang, seuls les rangs du catalogue comptent (pas de mélange des deux espaces de rang) ; sinon l'ordre bootstrap `_PRIORITY_SERVICE_ORDER` s'applique à l'identique. `homelab.{public,internal}.priority_source` vaut `catalog` ou `bootstrap`. Tests : priorité catalogue, débordement classé, repli bootstrap, validation stricte, propagation par override.
- [ ] **Supprimer le repli bootstrap** — après publication de `probePriority` dans `nabla-compose` (et correction du doublon LanguageTool qui fait rejeter le catalogue distant) : constater `priority_source=catalog` sur FastAPI Cloud et TrueNAS, puis supprimer `_PRIORITY_SERVICE_ORDER`. Le catalogue bootstrap embarqué reste une copie fidèle de `nabla-compose` : ne pas y ajouter de rangs avant l'amont.


- [x] **P0 Cloudflare Access probe evidence — export et tests (2026-10-17)** — les tests existants du runner (30) passent localement ; les champs `cloudflare_access_secondary_probe_eligible`/`_attempted`, `public_probe_verification`, `public_probe_auth_mode`, `anonymous_http_status`, `origin_reached` et `cloudflare_service_token_rejected` sont désormais **exportés** dans les lignes réconciliées `homelab.services` (auparavant seulement dans les résultats bruts). Tests ajoutés : éligibilité explicite (Access requis + 302/403 seulement), export, et redirection Access jamais `ok`, même avec une origine LAN saine. Relevé workstation : IT Tools `302` Access public + `200` LAN ⇒ `access_protected_origin_unverified`, `warn` ; KaraKeep `302` Access public mais **timeout 5 s en LAN sur :30147** ⇒ `warn`, `internal_state=fail` — l'edge répond, l'origine non.
- [ ] **KaraKeep : origine LAN injoignable** — `http://172.17.0.24:30147/` expire (5 s) depuis la workstation le 2026-10-17 alors que l'edge Cloudflare répond. Preuve d'acceptation : état de l'app TrueNAS (`/api/homelab/runtime`) et port réel comparés au catalogue ; corriger le port déclaré ou l'application, puis LAN `200` et `public_probe_verification=authenticated_origin_observed` avec un service token.
- [ ] **P0 Cloudflare Access probe evidence — service token** — prouver le cas `authenticated_origin_observed` en production avec un service token Access réel (FastAPI Cloud), et le cas `cloudflare_service_token_rejected=true` par un token révoqué de test ; exporter et tester `cloudflare_access_secondary_probe_eligible`, `cloudflare_access_secondary_probe_attempted` et `public_probe_verification` afin de différencier HTTP 403 anonyme protégé, service token refusé et origine réellement sondée. Vérifier les cas IT Tools et Karakeep contre réponses anonymes et résultats LAN, sans convertir un refus Access en application saine.


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

## P0 — Acceptation terrain FastAPI / Garage (2026-10-17)

- [x] **PR #342 fusionnée et acceptation staging** — checkout FastAPI `5fe39a33` ; trois sondes LAN Garage présentes, toutes `internal_state=ok`, sur deux campagnes de trois cycles ; pas de preuve de panne d'origine. La couverture des observations monte de 14 à 24,4 % sans changer le nombre de sondes par cycle.
- [x] **Qualité réseau ponctuelle** — `docker exec -i` (Python) : DNS 47 ms, TCP 4 ms, TLS 13 ms vers l'edge Garage `188.114.97.2`. HTTP via curl ~0,1–0,6 s. Ces mesures écartent seulement un blocage permanent du chemin **testé** ; elles ne prouvent pas que les douze sondes parallèles et les contrôles Access respectent les 4 s.
- [x] **Instrumenter sans relancer ni augmenter le trafic** — temps de file (`queue_wait_ms`), DNS (`dns_probe_ms`), HEAD/GET (`http_request_ms`), sondage Access secondaire (`access_secondary_ms`), couverture des mesures via `probe_summary.public.timing`. Les sondes annulées restent sans timing (unknown), jamais 0 ms fictives. Acceptance du code sur staging **à venir** pour la PR #350.
- [ ] **P0 sécurité** — `garage-admin` est sain en LAN, mais `exposure_intent=internal` et `unexpected_tunnel_route=true` ; auditer la route Cloudflare puis la retirer après preuve/rollback, sans confondre 302 Access et atteinte de l'origine.
- [ ] **P0 sécurité** — depuis le LAN, `s3.int.albandrieu.com` retourne HTTP 403 via `82.66.4.247` : la NAT reflection reste une explication plausible. Exiger un test réellement *hors LAN* avant de conclure à l'exposition WAN ou modifier HAProxy/pfSense.
- [ ] **P1 qualité d'observation** — des cycles `state=stale` peuvent coexister avec d'anciennes observations Garage `ok` ; afficher l'âge/cache et distinguer source de cache et nouvelle preuve. Les séries Prometheus `nabla:service:synthetic_*` restent absentes alors que `nabla:telemetry:gatus_up=1` et `/-/ready` répond : telemetry UNKNOWN, pas service DOWN.
- [ ] **P1 attestation runtime cross-repo** — `build_revision=null` malgré build local réussi : `nabla-compose` doit transmettre le SHA contrôlé et ajouter une attestation OCI au digest de l'image, avec preuve de correspondance à l'API. Le Gitlink parent encore épinglé sur `8c4492d1` n'est **pas** une preuve de la version déployée ; ne pas mettre à jour le sous-module automatiquement.
- [ ] **P1 pré-publication PR #350** — refaire les tests ciblés et la quality gate local-first sur le **nouveau HEAD**, puis vérifier EditorConfig/SAST/tests/security sans GitHub Actions coûteuses. Ne pas merger automatiquement.

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
- [x] Upgrade transitive `smol-toml` to a version fixing CVE-2026-34027 through
  the pinned Node/npm toolchain. Done 2026-10-17: the bounded `overrides` entry
  moved from `^1.6.1` to `^1.9.0` (lock resolves `1.9.1`) with mise Node 26 /
  npm 12. The `1.6.1` lock carried the `>=1.7.1` advisory that Trivy reports as
  `CVE-2026-85730` (GitHub `GHSA-7w5x-hrqm-74c2`; the earlier roadmap ID did
  not match any smol-toml advisory) and Dependabot alert #399
  (`GHSA-r4xh-jqrq-34v2`, fixed `1.9.0`). Both disappear from
  `trivy fs --include-dev-deps` and `npm audit --package-lock-only`.
  - [ ] Residual: `vercel@64.5.0` (latest) still pins `smol-toml` `1.5.2`
    exactly, so the override cannot be dropped by bumping the parent. Remove
    the override once `vercel` (and `@vercel/*`) depend on `>=1.9.0`;
    acceptance: `npm ls smol-toml --package-lock-only` resolves `>=1.9.0`
    without the override.
- [x] Reduce the Trivy baseline and make relevant triaged findings blocking.
  Done 2026-10-17: removed the four unmatched vulnerability suppressions
  (transformers `CVE-2023-6730`/`CVE-2023-7018`/`CVE-2024-3568`, Go
  `CVE-2024-24790`; `trivy fs --show-suppressed` matched none); every
  remaining misconfiguration/license entry still matches a finding. MegaLinter
  `REPOSITORY_TRIVY` is now blocking (`REPOSITORY_TRIVY_DISABLE_ERRORS: false`)
  on its triaged scope (production npm deps, fixed findings, vuln/misconfig/
  secret/license), which is clean with mise-locked Trivy `0.74.0`;
  `bash scripts/run-trivy.sh` reproduces it locally with `--exit-code 1` and
  `tests/unit/test_trivy_baseline_contract.py` keeps both argument lists equal.
  - [ ] Residual: the blocking scope still skips `uv.lock`/`Pipfile.lock` and
    npm dev dependencies. A full local scan (`--include-dev-deps`, no lockfile
    skips) shows 31 npm dev findings (`ip-address`, `undici`, `brace-expansion`,
    `toml`, `mysql2`, `tar`, ...), 12 `uv.lock` findings (10 fixable:
    `starlette` up to HIGH, `gradio`, `jupyter-server`, `mcp`, `aiosmtplib`)
    and the stale
    `Pipfile.lock` backlog (`gitpython`, `pyjwt`, `cryptography`, `anyio`).
    Acceptance: upgrade or document each, retire or regenerate `Pipfile.lock`,
    then extend `scripts/run-trivy.sh` and `.mega-linter.yml` to `uv.lock`
    with a clean local run before making it blocking.
    - [x] 2026-10-17 (PR #350): `jupyter-server` 2.20.0 → 2.21.0
      (GHSA-c3mw-737p-c7g2, HIGH); `uv.lock` with dev deps 11 → 10 findings.
      Superseded: Jupyter (`notebook`/`nbdev` group, `jupyterlab`, `notebooks/`,
      the compose `datascience-notebook` service, nbQA and `JUPYTER_JUPYFMT`)
      was removed on `chore/uv-only-fastapi-frontend-20261017`; `uv.lock` no
      longer contains `jupyter-server` (61 packages dropped).
    - [x] `starlette` ≥ 1.3.1 (runtime, 5 advisories incl. 2 HIGH), `gradio`
      ≥ 6.16.0 and `aiosmtplib` ≥ 5.1.2 (via `fastapi-mail` ≥ 1.6.3) are all
      blocked by `arel` 0.4.0 (`starlette==0.*`, debug hot-reload in
      `nabla/app_factory.py`); a dry run without `arel` resolves starlette
      1.8.0. Acceptance: remove/replace `arel`, migrate `add_event_handler` to
      lifespan (removed in Starlette 1.0), `uv lock` resolves the fixed
      versions and Trivy no longer reports these 8 findings.
    - [ ] `diskcache` (GHSA-w8v5-vhqr-4h9v) and `git-url-parse`
      (GHSA-4xqq-73wg-5mjp) have no upstream fix: drop `dvc-s3`/`git-url-parse`
      from the `extra` group or document risk acceptance.
    - [x] `Pipfile.lock` (62 findings, 5 CRITICAL) is still consumed by
      `make prepare-pipenv`/`setup-jupyter-local*`, `Dockerfile-pipenv` and the
      `.envrc` pipenv bootstrap: retire them together with a uv alternative for
      `setup-jupyter-local`, or regenerate with pipenv.
    - [x] 2026-10-17 (branch `chore/uv-only-fastapi-frontend-20261017`):
      `arel` removed (the debug reload is now a FastAPI SSE stream,
      `nabla/dev_reload.py`), FastAPI `0.143.3`, Starlette `1.8.0`
      (`fastapi-mail` 1.6.8, `gradio` 6.30.0,
      `prometheus-fastapi-instrumentator` 8.1.0, `sqladmin` 0.32.0,
      `aiosmtplib` 5.1.3). `Pipfile`, `Pipfile.lock`, `Dockerfile-pipenv` and
      the pipenv bootstraps (`.envrc`, `make prepare-pipenv`,
      `scripts/run-install.sh`) are retired; the packages the scripts still
      import live in the opt-in `scripts` group. Local
      `trivy fs --scanners vuln` on `uv.lock`: master 5 (Starlette) → 0.
      Pipfile dev-only tools not migrated: ansible-builder/navigator/
      playbook-grapher/runner, molecule, jira, jupyterlab extensions, poetry,
      autopep8/pep8/pep8-naming, cz-conventional-gitmoji (install with
      `uvx`/mise when needed).
    - [ ] Residual: `uv.lock` remains in `--skip-files` of
      `scripts/run-trivy.sh` and `.mega-linter.yml`. Acceptance: once this branch
      (rebased on PR #350) is merged, drop the skip and get a clean `bash scripts/run-trivy.sh`.
    - [ ] Residual: Starlette 1.8 warns that `starlette.testclient` with
      `httpx` is deprecated (`httpx2`). Acceptance: migrate the test client
      dependency once `httpx2` is supported by FastAPI's `TestClient`.
  - [ ] Residual: the image scan in `docker-build.yml` (Trivy action `v0.71.2`,
    no ignorefile, no `exit-code`) stays report-only and differs from the
    mise-locked `0.74.0`. Acceptance: align the version, triage the first image
    SARIF, then add `exit-code: 1` on fixed CRITICAL/HIGH findings.
  - [ ] Residual: MegaLinter `v10.0.0` bundles its own Trivy and downloads the
    DB at run time; prove the first blocking MegaLinter run on this scope is
    green (or reproduce any failure with `bash scripts/run-trivy.sh`), and
    treat DB-download/rate-limit errors as infrastructure, not findings.
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
- [x] Remove the `# noqa: C901` exemptions added (2026-10-14) so repo-wide
  `ruff check .` passes: split `get_or_refresh_probe` (complexity 28),
  `append_truenas_api_stages` (15), `TrueNASClient.health_snapshot` (14),
  `_query_fixed_metrics` (17, from #338), `compare_internal_probe_evidence` (13),
  `_security_filter_observations` (12),
  `public_topology_payload`, `check_pfsense_api` and the diagnose script
  `print_table` (11) below the McCabe limit of 10. Done 2026-10-17 without
  behavior change (helpers kept in the same modules so test monkeypatch targets
  stay valid; pfSense service-inventory classifiers moved to
  `nabla/api/pfsense_service_inventory.py` to keep `pfsense_dns_observer.py`
  under the 700-line limit). The older file-level `C901` exemption of
  `nabla/api/health_routes.py` (`register_health_routes`, 20) was also removed
  by splitting route registration into ordered groups (route list and OpenAPI
  schema verified identical to `master`); only `PLC0415` remains there.
- [ ] Residual: vendored cookiecutter hooks `ccds/hook_utils/configure_gh.py`
  (`configure_github_repo`, 18) and `ccds/monkey_patch.py`
  (`prompt_for_config`, 12) still exceed C901 behind blanket `# ruff: noqa`
  directives. Acceptance: remove the blanket directives and
  `ruff check --select C901 --ignore-noqa .` reports no finding.
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

- [x] 2026-10-17 (branch `chore/uv-only-fastapi-frontend-20261017`): the
  default app starts without PostgreSQL, Redis or Keycloak. PostgreSQL failure
  logs `startup_dependency_degraded … critical=false`; DB-backed routers
  (`/auth/*`, `/users/*`, `/notes/*`) answer 503 through
  `nabla.api.db.availability.require_database`; `/readyz` answers 200
  `degraded` with `required: false` per check; `/healthz` no longer treats
  PostgreSQL/Redis as required. `POSTGRES_REQUIRED=true` / `REDIS_REQUIRED=true`
  restore fail-fast startup and readiness. Keycloak settings are optional, the
  client is built lazily (`get_keycloak_openid`), the `/healthz` probe is
  `skipped` and the Keycloak auth routes answer 503 when unset. Live proof on
  a workstation without Postgres/Redis/Keycloak: `make up` → `/livez`,
  `/readyz`, `/` 200, `/notes/` and `/users/me` 503, no traceback.
  - [x] Required dependencies follow `runtime_mode()`: FastAPI Cloud →
    Redis + Supabase; TrueNAS (`FASTAPI_RUNTIME_MODE=homelab`) → Redis +
    PostgreSQL, with fail-fast PostgreSQL startup; workstation (`local`) →
    none. `POSTGRES_REQUIRED`/`REDIS_REQUIRED`/`SUPABASE_REQUIRED`
    (`true|false`) override the default. `runtime_topology_heartbeat_failed`
    warns once per Redis outage (then debug, `…_recovered` on return).
  - [ ] Residual: deployed acceptance proof. Acceptance: after deployment,
    `/readyz` returns 503 on FastAPI Cloud when Redis or Supabase is stopped and
    on TrueNAS when Redis or PostgreSQL is stopped, and the contract is
    documented in the nabla-compose runbook (owner: `nabla-compose`).
  - [x] Workstation log hygiene: `make up` runs `ddtrace-run` only with
    `DATADOG_ENABLED=true`; Supabase is required on FastAPI Cloud and
    PostgreSQL on TrueNAS (never both); without Unleash every flag is off
    instead of raising (the `/stream` SSE no longer fails); local 503s,
    missing TrueNAS credentials and optional PostgreSQL/Redis outages log at
    most one warning. Live proof: `make up` on the workstation →
    `/v1/runtime/errors` empty, no traceback.
  - [ ] Residual: Sentry initialises `target=cloud` on the workstation, so dev
    errors reach the cloud Sentry project. Acceptance: a workstation profile
    (no DSN or a dev DSN in `.env.local`) confirmed by
    `/v1/runtime/metadata`/startup logs.
  - [ ] Residual: gunicorn `--reload` (`make up`) logs `Worker reloading`
    but the UvicornWorker never restarts, so code changes need a manual
    restart. Acceptance: reproduce, fix (e.g. `fastapi dev`/uvicorn reload for
    local dev) and show a reload picking up an edit.
  - [ ] Residual: on this workstation `/healthz` took ~8 s without
    dependencies. Acceptance: attribute the slow checks from `probe_budget`
    and keep the deep diagnostic under its budget.

- [x] Introduce an application factory so tests can create a minimal app without
  PostgreSQL, Redis, observability, MCP or RAG side effects:
  `nabla.app_factory.create_app(AppFeatures(...))` with
  `nabla.app_features.AppFeatures` switches and
  `nabla.lifespan.build_lifespan(features)`; `nabla.main:app` keeps the
  all-enabled production contract (PostgreSQL stays critical) and its OpenAPI
  path set is unchanged. Local diagnostics without PostgreSQL:
  `uv run uvicorn --factory nabla.app_factory:create_minimal_app`. Hermetic
  proof: `tests/unit/test_app_factory.py` (socket/DB/Redis/MCP I/O forbidden).
  - [ ] Residual: importing the factory still imports `nabla.api`, which builds
    the module-level SQLAlchemy engine/psycopg pool/`databases` handle and the
    unconnected Redis client (no I/O). Removing those globals belongs to the
    next item; acceptance proof: importing `nabla.app_factory` and building the
    minimal app leaves `nabla.api.db.database` and
    `nabla.api.demo.socket.redis` absent from `sys.modules`.
  - [x] `/readyz` and `/api/runtime/topology` read `app.state.features`
    (2026-10-17, PR #350): disabled subsystems are reported `disabled`/
    `skipped` without probing and do not fail readiness; enabled ones fail as
    before. The default app only gains an additive `subsystems` field (OK→200,
    PostgreSQL down→503 unchanged). Live proof:
    `uv run uvicorn --factory nabla.app_factory:create_minimal_app` with an
    invalid `POSTGRES_HOST`/`REDIS_URL` → `/readyz` HTTP 200 `ready`, all five
    subsystems `disabled`.
  - [ ] Residual: the minimal app's `/api/runtime/topology` still calls
    `observe_public_egress_ip()` (outbound HTTP); gate it on a feature and test
    with sockets forbidden and no mock.
  - [ ] Residual: `/healthz` and the health-board
    (`nabla/api/health_board_diagnostics.py`) still ignore features; acceptance
    proof: both report PostgreSQL/Redis `disabled` without I/O in the minimal
    app.
  - [ ] Residual: no environment switch selects features for `nabla.main:app`
    or FastAPI Cloud; acceptance proof: a documented, tested
    environment-to-`AppFeatures` mapping if operators need it.
  - [ ] Residual: live LAN acceptance of the minimal app against homelab
    diagnostics (`/api/homelab/status`, `/api/homelab/health`) on the operator
    workstation has not been recorded.
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
  Inventory done in `fix/notes-contract-20261017` (PR description); the item
  stays open until the residuals below are closed.
  - [x] Make `completed` a real boolean across request/response, persistence and
    serialization; retain backwards compatibility only when consumers require it.
    Legacy string spellings (`"True"`/`"False"`) remain accepted on input and
    when reading not-yet-migrated rows.
  - [x] Use timezone-aware UTC timestamps and test input/output normalization.
    `created_date` is ISO 8601 UTC (`...Z`); naive legacy values are read as UTC.
  - [x] Define typed read/delete responses, explicit 404/403 behavior and
    authorization-preserving CRUD tests. Notes have no owner column and no
    auth dependency, so no 403 path exists; tests pin that notes CRUD stays
    out of `MCP_ALLOWED_ROUTES`.
  - [x] Verify database migration and roundtrip integration in an isolated DB;
    do not rewrite production rows without reversible migration evidence.
    Alembic `4b7c2d9e1a6f` upgrade/downgrade/re-upgrade and the CRUD roundtrip
    (`tests/integration/test_notes_postgres.py`) passed on a disposable local
    PostgreSQL 17 container.
  - [ ] Residual — production/staging rollout: before `alembic upgrade head`,
    take a backup and run `SELECT DISTINCT completed FROM note` (any value
    outside true/false spellings aborts the migration) and confirm the server
    clock that wrote naive `created_date` values was UTC. Acceptance proof:
    `alembic current` = `4b7c2d9e1a6f` and `GET /notes/{id}/` returns a boolean
    `completed` and a `Z` timestamp on the target environment.
    Owner confirmation (2026-10-17): the `note` table is currently empty, so no
    existing row is converted and the value/clock pre-checks have no data to
    validate; the post-migration acceptance proof above still applies.
  - [x] Alembic baseline (2026-10-17, PR #350): `992855f73a8d` is now a
    tolerant baseline (creates `user` with the fastapi-users UUID shape,
    legacy `note` and `sensor_reading` only when absent; revision ids
    unchanged) and `alembic/env.py` targets `application_metadata()`
    (`nabla/api/db/metadata.py`). On a disposable PostgreSQL 17: empty DB →
    `upgrade head` → `downgrade base` → `upgrade head`; `create_all` + row +
    stamp `4b7c2d9e1a6f` keeps the row; `create_all` + stamp `992855f73a8d`
    and unstamped `create_all` both upgrade cleanly; `compare_metadata` is empty
    at each step. Opt-in `tests/integration/test_alembic_postgres.py` (5 cases).
  - [ ] Residual — real databases: on each deployment check
    `SELECT version_num FROM alembic_version` is `992855f73a8d` or
    `4b7c2d9e1a6f` and `user.id` is `uuid`, then `alembic upgrade head`.
  - [ ] Residual — offline `alembic upgrade head --sql` is unsupported (both
    revisions inspect the live schema); document or add offline branches.
  - [ ] Residual — run `-m integration` (Alembic + Notes) in CI with a
    disposable PostgreSQL service once CI capacity returns.
  - [ ] Residual — note ownership: add an owner column and 403 semantics only
    if notes become per-user data (product decision), with cross-user tests.
  - [x] HTMX form routes (2026-10-17, PR #350): templates now target the real
    unprefixed routes (`/notes/`, `/notes/add`, `/notes/{id}`,
    `/notes/{id}/edit|toggle|delete`); `POST /notes/add` reads the form field,
    edit merges into `NoteData` through `crud.put` (no record mutation,
    `created_date` kept), toggle/delete routes added because the templates call
    them, fields renamed to `completed`/`description`, explicit 404.
    `tests/unit/test_notes_htmx.py` (15 hermetic cases) also asserts every
    `hx-*` call maps to a declared route.
  - [ ] Residual — browser + PostgreSQL acceptance of list/add/edit/toggle/
    delete from `/` on a disposable DB at `4b7c2d9e1a6f` (or extend
    `tests/integration/test_notes_postgres.py` to these routes).
  - [ ] Residual — a stored row violating `NoteResponse` constraints makes
    toggle/update fail with a 500 validation error; return 422/409 explicitly.
  - [ ] Residual — `POST /notes/add` hard-codes `description`/`type`/`prompt`
    and form routes do not enqueue Redis work unlike `PUT /notes/{id}/`
    (product decisions); fragments still start with `<!doctype html>`.
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
