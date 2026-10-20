# Engineering backlog — outstanding legacy checklist items

Extracted from the historical roadmap at [commit 594d51d64efd](https://github.com/AlbanAndrieu/fastapi-sample/blob/594d51d64efdd5274d2ba42a9cb09551b6d57d46/docs/engineering-roadmap.md).
Only unchecked tasks were retained below; completed implementation narratives
remain recoverable from code, tests and Git history.

**These unchecked entries are historical hypotheses, not verified current debts.**
Before executing one, reconcile it with current code, PRs and runtime. The
active priority order is in [engineering-roadmap.md](engineering-roadmap.md).
Incident-specific forensic evidence and recovery procedures remain in
[incidents.md](incidents.md) and the nabla-compose runbooks.

## P0 — Master-red : acceptation terrain après fusion

- [ ] Constater deux **runs post-merge consécutifs et réellement réussis**
  du workflow `master-red-remediation.yml`, au HEAD actuel de `master`.
  Les `skipped` sont acceptables uniquement lorsque le scan était optionnel.
  L'issue unique [#355](https://github.com/AlbanAndrieu/fastapi-sample/issues/355)
  garde la description/les labels édités manuellement ; le robot ne pilote
  que son propre commentaire, sauf clôture justifiée par deux succès.

## P1 — DefectDojo : producteur FastAPI → collecteur Nabla

- [ ] Accepter l'artefact master FastAPI, son manifeste SHA/empreinte, le
  parseur réel DefectDojo, l'engagement précréé et la déduplication après
  traitement asynchrone. Vérifier un refus RBAC inter-produit.
- [ ] Définir l'archivage **chiffré, privé et à durée limitée** des rapports
  bruts si une investigation ultérieure doit retrouver les données filtrées.
  Aucun rapport original n'est récupérable après expiration s'il n'a pas été
  conservé séparément.
- [ ] Valider le parser `CodeQL Scan` sur un SARIF d'origine vérifiable et
  empêcher un double import par parser SARIF générique.

## P0–P2 — Chaîne de sécurité locale, rapports privés et DefectDojo (2026-10-18)

- [ ] **PR obligatoire** : garantir sur la vraie gate de publication locale que Betterleaks et Trivy `CRITICAL/secret` ne sont ni ignorés ni transformés en succès à cause d'un scanner manquant, d'un échec de parsing ou d'un rapport incomplet ; CodeQL déjà planifié sur modifications Python. Vérifier les conclusions GitHub sur le SHA exact sans démultiplier les jobs.
- [ ] **DefectDojo UI / Vaultwarden** : dans `nabla-compose`, après diagnostic runtime, créer un opérateur UI non administrateur avec identifiant distinct, mot de passe généré cryptographiquement (au moins 32 caractères), puis enregistrer l'item dédié dans Vaultwarden par CLI sans écrire le secret en Git, logs, stdout ou artifacts. Compte de service API *distinct* et restreint au seul produit/engagement `fastapi-sample`; provisionnement effectif **NOT_RUN**.
- [ ] **Ingestion privée sans scraping entrant** : product/engagement IDs préexistants, `reimport-scan` en sortie depuis runner LAN, manifestes et checksums SHA-256, aucune donnée Betterleaks brute ou secret Trivy, aucun token Dojo en navigateur/CDN ; garder l'import strictement limité à `fastapi-sample` et refuser les formats non validés. Aucun import de rapports provenant d'autres projets n'est développé ici.
- [ ] **DAST coordonné et parcimonieux** : pas de DAST complet sur chaque PR ; établir la liste exacte des hosts autorisés dans `*.albandrieu.com` (pas de wildcard de scan), exclusions explicites pfSense/TrueNAS Admin et endpoints mutatifs. Réutiliser le ZAP/Nuclei de `nabla-site-alban` plutôt que doubler les mêmes cibles ; scans profonds sur `master` ou depuis le LAN après approbation, limites de débit et rétention courte.
- [ ] **P0 Compte UI / Vaultwarden dans `nabla-compose`** : utilisateur UI humain non superuser, mot de passe 32+ caractères généré depuis RNG cryptographique et item dédié dans Vaultwarden. Créer **séparément** un utilisateur API d'import à droits réduits sur l'engagement `fastapi-sample`, avec jeton lu uniquement depuis un fichier privé sur le runner LAN ; ne pas confondre token DefectDojo (authentification) et ACL produit/engagement (autorisation). Vérifier les permissions réellement disponibles dans l'édition OSS/Pro. Aucun provisionnement exécuté. Parité avec `scripts/truenas/prepare-security-tooling-secrets.sh`, bootstrap Vaultwarden et diagnostic `diagnose-defectdojo.sh`. Marquer `NOT_RUN` jusqu'à provisionnement effectif.
- [ ] **P1 RBAC et traitement asynchrone** : attacher le jeton de service à une identité non-superuser ne disposant de l'écriture que sur le produit/engagement `fastapi-sample` ; ID fixe hors Git, parser exact contrôlé depuis l'instance, `test_title` stable, `auto_create_context=false`, `close_old_findings=false`. Ajouter un suivi en lecture seule `GET /api/v2/tests/{id}/` jusqu'à `Processed` ou `Failed`; un 200/201/202 d'upload n'est pas une preuve de findings ingérés.
- [ ] **P1 Acceptation LAN-only et pare-feu** : vérifier le split DNS Pi-hole/Unbound, le TLS Host/SNI Traefik, les routes et bindings `172.17.0.24:31085`, les ACL inter-VLAN et les éventuels NAT/HAProxy WAN (y compris accès direct par IP+Host forgé). Défense en profondeur : accès API limité aux IPs des importateurs et aucun DNS/Cloudflare Tunnel public DefectDojo. **NON PROUVÉ en live dans cette PR** ; le pin réseau n'est pas la preuve d'une ACL pfSense.
- [ ] **Gates d'acceptation** : tests vrais `trivy`, `betterleaks`, `semgrep`, `nuclei`, ZAP selon mode, rapports présents/non tronqués, import DefectDojo HTTP 2xx suivi du job asynchrone et dédup, preuve de `Critical=0` et secrets=0 sur HEAD exact. Aucun contournement des diagnostics ou scanning de sous-domaines `*.albandrieu.com` non autorisés.
- [ ] **P2 DAST / couverture** : coordonner site `www.albanandrieu.com`, API Cloud `fastapi-sample.fastapicloud.dev` et staging `sample.albandrieu.com` uniquement derrière contrôle explicite. DAST passif, scope strict, chemins dangereux exclus, plafonds temps/RPS, scans plus complets `master` ou déclenchement manuel plutôt qu'un par PR ; compléter Semgrep, ZAP, Nuclei selon lacunes réelles plutôt que les dupliquer.

## P0/P1 — Validation JWT Cloudflare et WebSocket ASGI (PR #353)

- [ ] **Acceptance G1/G4** : tests de signature JWT local RS256, réseau JWKS en erreur, mauvaises audiences, Service Token et identité ; vérifier WebSockets/mounts du vrai runtime, migration des consommateurs A2A/WebSocket et reverse proxies avant déploiement. Tant que ces tests et `OPS_ROUTE_POLICY_STRICT` ne sont pas acceptés, la surface complète n'est **pas** sécurisée.
- [ ] L'activation de `ops.albandrieu.com`, du Tunnel et du MFA reste conditionnelle aux gates G2–G5 ; Keycloak différé. Pas de fusion automatique.

## IMPLEMENTED CODE — RoutePolicy + DTO strict (PR #353, 2026-10-18)

- [ ] **G1 — migration compatibilité avant activation runtime** : le nouveau code ferme des endpoints auparavant anonymes (dont `/api/public-topology`, `/api/health-board`) ; réconcilier les lecteurs Vercel et l'UI cloud, prévoir rollback. Ne pas merger/déployer tant que ces clients n'utilisent pas le DTO public et les identités privées.
- [ ] **G1 — couverture exhaustive** : `OPS_ROUTE_POLICY_STRICT` est **false par défaut** pour ne pas interrompre les routes legacy non classées pendant la migration. Activer `true` seulement après inventaire réel et revue des routes. Tant que false, les routes `REVIEW` sont encore passantes : **sécurité partielle, pas une frontière publique complète**.
- [ ] **G1/G4 — transports hors HTTP** : l'actuel middleware FastAPI ne protège **ni les WebSockets ni les mounts ASGI hors HTTP**. Implémenter une gate ASGI dédiée, tests `ws_connect`, A2A/MCP et tests d'accès direct origine avant `ops`.
- [ ] **G1–G5** : vérification JWT RS256/JWKS, audience/issuer/subject, credentials machine distinctes, déploiement Access/Tunnel, contrôles hors LAN et scans publics toujours NOT_RUN. Keycloak différé.

## CURRENT EXECUTION ORDER — confidentialité API publique / ops.albandrieu.com (PR #353, 2026-10-18)

### Ce que cette PR apporte sans effet runtime

- [ ] Exécuter l'inventaire des routes réellement enregistrées sur le HEAD exact, compléter une matrice par méthode/route, détecter les alias, mounts et routes OpenAPI. Une route non classée ne doit jamais devenir publique ; enregistrer des preuves assainies.
- [ ] **Séquence anti-divulgation** : corriger d'abord le site public et les exports statiques, puis déployer l'autorisation fail-closed sur FastAPI Cloud et TrueNAS. Les diagnostics et la sonde outside-in du cloud restent distincts des preuves LAN de Gatus.
- [ ] Après validation de la PR, démontrer G0→G5 en ordre ; aucun DNS, policy Access, Keycloak, firewall, déploiement ou merge dans cette PR.

## P1 — Campagnes distinctes et diagnostics local-first (PR #350, 2026-10-18)

- [ ] **Validation locale du dernier HEAD** — les 30 tests ciblés étaient verts sur TrueNAS à `aa2491b5`; Ruff C420 a été corrigé dans `e887499d`, mais la gate et les nouveaux tests de déduplication devront être exécutés sur le commit courant avec `UV_PYTHON=/usr/bin/python3.13` et `TMPDIR` exécutable. Ne pas transférer la preuve de tests d'un ancien SHA.
- [ ] **Acceptation runtime ultérieure** — seulement après validation locale et déploiement volontaire du SHA immuable, réunir au moins trois identifiants `homelab.checked_at` distincts via le script de synthèse et comparer `deadline_phase_counts` aux expirations. Aucun merge ni déploiement automatisés.

## P1 — Sondes Garage : preuve de phases et comparaison des cycles (PR #350)

- [ ] **Acceptation du prochain SHA de PR** — après déploiement volontaire d'une version validée, comparer au moins trois vagues `probe_cache.source=origin` avec `deadline_phase_counts`, les phases des entrées `deadline` et les dernières tentatives sur preuves `memory`. Ne pas confondre cache, succès réseau et deadline. Ne pas augmenter budget 4 s, concurrence 4 ni échantillonnage 12.
- [ ] **Optimisation conditionnée aux mesures** — si l'attente sémaphore domine, examiner la contention commune LAN/public et la durée de retenue ; si le DNS domine, examiner la résolution explicite A/AAAA et HTTPX. N'éliminer ou paralléliser aucune sonde ni phase de sécurité avant acceptation de la nouvelle attribution.
- [ ] **Contrôles finaux différés sur demande opérateur** — conserver les hooks EditorConfig, SAST/DAST et la gate de publication inchangés ; les exécuter avant fusion, pas pendant cette itération de développement.

## P1 — Catalogue de criticité et sondes par unité de déploiement (2026-10-17)

- [ ] **Acceptation avant raccordement runtime** — publier réellement le schéma canonique dans `nabla-compose` (PR #257 actuellement metadata staging), inclure la révision du catalogue et un modèle typé, puis comparer l'aperçu avec les consommateurs existants. Le budget de 12 reste en *unités sélectionnées* ; déterminer séparément le budget HTTP réel par composant, les conditions de sondage Admin et le verrou singleflight avant tout déploiement.
- [ ] Reconcile canonical `x-nabla` and its catalog-v2 revision with FastAPI package fallback, origin and live TrueNAS apps. Preserve the existing direct v2 cutover plan (no permanent v1/v2 shim).
- [ ] Distinguish `operationalCriticality` from BIA-derived `businessCriticality`; do not infer business criticality from display role or use a missing value as Low. Reuse catalog unit-level `stateful`, `upgradePolicy` and dependency metadata for *display/observation*, not an administrative Docker control plane.
- [ ] Add normalized `deploymentUnitId`, logical endpoint/member relations, `probePolicy` and ordered dependencies in the canonical catalog. The keys `garage` (S3 :3900), `garage-admin` (Admin :3903) and `garage-webui` (UI :3909) remain distinct but share `truenas:garage` for scheduling, caching and upgrade-policy grouping.
- [ ] Replace three parallel Garage fan-outs with a bounded, serialized, cache-aware **per-unit** probe sequence: primary read-only S3 probe, conditional Admin probe and WebUI probe, with shared cooldown, singleflight, capped concurrency and per-endpoint evidence/staleness. Use the dependency DAG for ordering; separate internal and outside-in observers. Never repeatedly hammer Admin API or Cloudflare Access.
- [ ] Preserve #342's **12-target sampling budget with 10 prioritized + 2 rotating slots**, rotating across units and independently tracking component coverage; prevent starvation even if selected units have multiple endpoints. A group counts as one scheduling selection, **not** a promise of unlimited probes.
- [ ] Preserve independent health vs exposure intent: `external=false` requires LAN validation and outside-in exposure audit; Cloudflare 302/403 does not prove origin health or exposure; stale/missing LAN evidence must not turn DOWN or GREEN without proof. Timeouts become warning/unknown, not speculative runtime DOWN.
- [ ] Add regression tests for Garage unit deduplication, priority order, no-starvation rotation, 1–3 target budgets, TTL and stale evidence, access-protected probes, and conservative degradation. Measure probes/minute, concurrency, latency and TrueNAS/pfSense CPU before/after. Avoid changing the production cloud's no-LAN-probe posture.
- [ ] Publish unit-level summary + per-component evidence and provenance on health-board only after local-first quality gate, synchronized catalog revisions and accepted rollback plan.
### P0 — Garage absent des cartes de `/api` (2026-10-17)

- [ ] **Publication locale** — exécuter les tests ciblés JS/Python, le formatage/EditorConfig et `agent-publish.sh` sur le nouveau HEAD propre ; pas de coût GitHub Actions induit par un `[skip ci]`.
- [ ] **Acceptation staging/navigateur** — seulement après un déploiement du nouveau SHA avec rollback : vérifier trois cartes, la recherche « garage », le filtre « At risk » pour Admin, « Internal-only » pour les API, et l'absence de lien public sur l'Admin et le S3. Le staging actuel `5fe39a33` n'embarque pas ce correctif.
- [ ] **Ancienne erreur quality gate dans worktree détaché** — le premier `uv run --no-sync pytest` a créé une `.venv` vide (`starlette` absent). La passe `--fix` a ensuite laissé quatre fichiers modifiés et `agent-publish.sh` les a refusés (comportement attendu). Une fixture imbriquée `test_agent_publication_proof` a aussi retourné exit 30 dans ce contexte ; conserver sa sortie complète pour attribuer ce cas si un HEAD propre le reproduit, sans neutraliser ce test. Le HEAD concurrent `2902b13b` dispose déjà d'une preuve workstation de quality gate verte, non transférable au futur commit UI.

## P1 — Garage : couverture des sondes LAN et reconciliation DNS (2026-10-13)

- [ ] **P0/P1 — Identifier l'origine des expirations publiques variables** — après déploiement #342 : `completed/timed_out=1/11,1/11,11/1` puis `11/1,1/11,12/0` avec le **même budget 4 s**, sans défaillance LAN Garage. Résolution DNS/TCP/TLS Python directe depuis le conteneur vers `garage.albandrieu.com` : **47/4/13 ms**, IP edge `188.114.97.2`. HTTP curl hôte/conteneur ~0,1–0,6 s ; les temps curl DNS/connect/TLS sont cumulatifs et ne prouvent pas une panne egress. Prioriser contention du sémaphore partagé interne/public, volume de requêtes HEAD/GET, éventuelles sondes secondaires Access hors sémaphore et cache/stale ; analyser les nouveaux `probe_summary.public.timing` et `public_probe_results[].probe_timing` en comparant `completed_samples` avec `timed_out`, sans relever le budget ni solliciter pfSense.
- [ ] **Cross-repo catalogue source et priorité** — les diagnostics TrueNAS 2026-10-17 constatent **une seule entrée LanguageTool locale** : l'ancien doublon ne doit plus être déclaré comme un incident actuel sans preuve sur le catalogue distant. Trois entrées Garage ont `probePriority=null`, `deploymentUnitId=null` et `priority_source=bootstrap`. Publier les métadonnées dans le catalogue autoritaire `nabla-compose` avec tests d'unicité/provenance puis confirmer `priority_source=catalog` ; aucune migration du fan-out vers les unités n'est activée dans cette PR.
- [ ] Auditer les origines actives Cloudflare Tunnel : `garage.albandrieu.com` a renvoyé du XML S3 ; le 2026-10-15, `garage-admin.albandrieu.com` renvoie `HTTP/2 302` vers le login Cloudflare Access. Cela confirme une route publique à l'edge, mais ne prouve pas l'accès anonyme à l'origine ni son port. Comparer les ports :3900/:3903/:3909, routes Access et contenu de réponse ; retirer l'ingress public Admin API après confirmation de sa source de configuration.
- [ ] Preuve d'acceptation : depuis un point de vue hors LAN (FastAPI Cloud ou réseau mobile), `curl -sS -o /dev/null -w '%{http_code}' https://s3.int.albandrieu.com/` ; si une réponse Garage arrive, la route HAProxy/NAT publique du S3 est réelle → la retirer ou la restreindre et supprimer l'enregistrement DNS public `s3.int` (côté `nabla-compose`/pfSense) ; retirer aussi la route tunnel publique `garage-admin`.
- [ ] Intégrer l'audit DNS public + HAProxy/NAT pfSense + Traefik + Cloudflare dans un rapport de drift `declared/observed/unknown`, avec preuves outside-in. La politique privée n'est pas une preuve d'inaccessibilité WAN.
- [ ] Collecteurs `cloudflare_tunnel` (API Cloudflare, lecture seule), `pfsense_nat_haproxy` et `traefik` (configuration) : à écrire avec des identifiants en lecture seule hors Git, puis publier le rapport complet sur le health-board.
- [ ] Évaluer accès privé distant via Tailscale/WireGuard pour retirer à terme la WebUI de l'Internet public ; en attendant, conserver uniquement l'UI publiable derrière contrôle d'accès.
- [ ] **Cross-repo `nabla-compose`** — déclarer la priorité de sonde dans le catalogue au lieu du code : ajouter un champ optionnel `probePriority` (entier, rang croissant, absent = rotation) dans `catalog/homelab-exposure-overrides.json`, avec validation de schéma côté `nabla-compose`. Regrouper par composant via `sourcePath` (ex. `apps/garage/compose.yml` → `garage`, `garage-admin`, `garage-webui`) plutôt que par liste d'identifiants. Ne pas dériver la priorité de `criticality` : 30 nœuds `critical`/`high` dépassent le budget de 12.
- [ ] **Supprimer le repli bootstrap** — après publication de `probePriority` dans `nabla-compose` (et correction du doublon LanguageTool qui fait rejeter le catalogue distant) : constater `priority_source=catalog` sur FastAPI Cloud et TrueNAS, puis supprimer `_PRIORITY_SERVICE_ORDER`. Le catalogue bootstrap embarqué reste une copie fidèle de `nabla-compose` : ne pas y ajouter de rangs avant l'amont.
- [ ] **KaraKeep : origine LAN injoignable** — `http://172.17.0.24:30147/` expire (5 s) depuis la workstation le 2026-10-17 alors que l'edge Cloudflare répond. Preuve d'acceptation : état de l'app TrueNAS (`/api/homelab/runtime`) et port réel comparés au catalogue ; corriger le port déclaré ou l'application, puis LAN `200` et `public_probe_verification=authenticated_origin_observed` avec un service token.
- [ ] **P0 Cloudflare Access probe evidence — service token** — prouver le cas `authenticated_origin_observed` en production avec un service token Access réel (FastAPI Cloud), et le cas `cloudflare_service_token_rejected=true` par un token révoqué de test ; exporter et tester `cloudflare_access_secondary_probe_eligible`, `cloudflare_access_secondary_probe_attempted` et `public_probe_verification` afin de différencier HTTP 403 anonyme protégé, service token refusé et origine réellement sondée. Vérifier les cas IT Tools et Karakeep contre réponses anonymes et résultats LAN, sans convertir un refus Access en application saine.
### P0 — Audit de sécurité Cloudflare (à réaliser)

- [ ] Examiner et valider la provenance, les permissions et les prérequis du dépôt officiel [cloudflare/security-audit-skill](https://github.com/cloudflare/security-audit-skill) avant installation (version/commit épinglé, principe du moindre privilège).
- [ ] Installer le skill dans un environnement isolé et exécuter **un audit en lecture seule** des zones Cloudflare pertinentes pour fastapi-sample et les services publics du homelab : Cloudflare Access, politiques, Service Tokens, WAF, tunnels, DNS et risques de contournement d'authentification.
- [ ] Enregistrer les résultats dans un rapport de sécurité **assaini** (sans jetons, identifiants sensibles ou secrets) ; distinguer constats vérifiés, points non accessibles et recommandations.
- [ ] Réconcilier les observations avec les sondes outside-in de FastAPI Cloud et les diagnostics TrueNAS, sans assimiler un service accessible à un service sécurisé ; produire des actions correctives testables et priorisées.
- [ ] N'appliquer **aucun changement de politique Cloudflare** automatiquement : revue et autorisation explicites avant toute modification ; valider ensuite l'absence de régression Access et le fonctionnement des Service Tokens.

## P0 — Acceptation terrain FastAPI / Garage (2026-10-17)

- [ ] **P0 sécurité** — `garage-admin` est sain en LAN, mais `exposure_intent=internal` et `unexpected_tunnel_route=true` ; auditer la route Cloudflare puis la retirer après preuve/rollback, sans confondre 302 Access et atteinte de l'origine.
- [ ] **P0 sécurité** — depuis le LAN, `s3.int.albandrieu.com` retourne HTTP 403 via `82.66.4.247` : la NAT reflection reste une explication plausible. Exiger un test réellement *hors LAN* avant de conclure à l'exposition WAN ou modifier HAProxy/pfSense.
- [ ] **P1 qualité d'observation** — des cycles `state=stale` peuvent coexister avec d'anciennes observations Garage `ok` ; afficher l'âge/cache et distinguer source de cache et nouvelle preuve. Les séries Prometheus `nabla:service:synthetic_*` restent absentes alors que `nabla:telemetry:gatus_up=1` et `/-/ready` répond : telemetry UNKNOWN, pas service DOWN.
- [ ] **P1 attestation runtime cross-repo** — `build_revision=null` malgré build local réussi : `nabla-compose` doit transmettre le SHA contrôlé et ajouter une attestation OCI au digest de l'image, avec preuve de correspondance à l'API. Le Gitlink parent encore épinglé sur `8c4492d1` n'est **pas** une preuve de la version déployée ; ne pas mettre à jour le sous-module automatiquement.
- [ ] **P1 pré-publication PR #350** — refaire les tests ciblés et la quality gate local-first sur le **nouveau HEAD**, puis vérifier EditorConfig/SAST/tests/security sans GitHub Actions coûteuses. Ne pas merger automatiquement.

## P0 integration checkpoint — Gatus / Prometheus / OpenRAG (2026-10-10)

- [ ] **Live acceptance BLOCKED (not PASS):** from this agent environment TCP
- [ ] Prove from inside the **FastAPI TrueNAS container** that
- [ ] Run the existing cached `/api/health-board` and diagnostic comparison
- [ ] Compare runtime identifiers with the authoritative `nabla-compose`
- [ ] Validate the focused synthetic comparison and platform-metrics tests,
- [ ] **OpenRAG decision:** inventory existing OpenRAG/Langflow/embedding

## CURRENT FASTAPI-SAMPLE DELIVERY SLICE — six workstreams (2026-10-11)

- [ ] Validate these checks with the complete local test module and

## P0 — production security and privacy

- [ ] Set `DEBUG=false` in FastAPI Cloud and prove unexpected exceptions no
- [ ] After the next authorized production deployment, verify the effective
- [ ] Audit retained FastAPI Cloud/Sentry/Logfire/centralized logs for credentials,
- [ ] Review historical commits containing private contact data and decide whether
- [ ] Replace shared operational keys with Keycloak/OIDC identities and explicit
- [ ] Finish the public homelab projection beyond topology. The browser topology
- [ ] Apply the intended Cloudflare Access/private-network restriction to
### P0 Prometheus telemetry reconciliation (2026-10-11)

- [ ] Validate recording-rule loading and actual samples from TrueNAS Prometheus; a declared scrape does **not** establish that an exporter is running or reachable. Keep missing optional series unknown, never DOWN.
- [ ] Evaluate Cloudflare **control-plane API metrics** independently; there is currently no verified Cloudflare Prometheus exporter/scrape job. Do not synthesize `cloudflare_up` or conflate Cloudflare API data with Prometheus evidence.
- [ ] Inventory other declared jobs (Kafka, ClickHouse, OpenSearch, Loki, Alloy, Tempo, Mimir, Keycloak, CrowdSec, DNS, HAProxy) and prioritize stable recording rules by operator value before extending the fixed contract.
### Prometheus service telemetry follow-up (2026-10-11)

- [ ] On TrueNAS, prove Prometheus rule-load success, per-job coverage and fresh samples. Exporter scrape `up=0` denotes unavailable *telemetry*, not automatically a failed application.
- [ ] Confirm whether a real Cloudflare exporter exists: the job label being configured in a rule is **not** evidence of a running exporter. Preserve the separate Cloudflare API observer and authenticated Access checks.
### Duplicate exporter-series contract (2026-10-11)

- [ ] On TrueNAS, compare source labels / target duplication if this diagnostic actually occurs; do not silently rewrite scrape jobs or restart Prometheus.
- [ ] Run focused tests and exact-HEAD local publication quality checks when a trustworthy checkout is available; no CI checks have been bypassed or declared green.
### Gatus Prometheus defensive aggregation (2026-10-12)

- [ ] Execute exact-HEAD tests and confirm that recording rules load and expected samples appear on TrueNAS. No runtime health claim is inferred from these code changes.
### Gatus label and cardinality guardrails (2026-10-12)

- [ ] Validate the real TrueNAS catalogue ID space and Prometheus samples, then adjust the contract through reviewed tests if an authorized service ID does not match. Complete exact-HEAD tests before merge.
### Gatus raw fallback conflict handling (2026-10-12)

- [ ] Test real Prometheus scrape target multiplicity and fix duplicate targets at the authoritative `nabla-compose` source if discovered. Record actual series freshness and validation output in the grouped TrueNAS acceptance campaign.

## P0 — homelab dependency convergence

- [ ] **Talos cluster health:** prove the guest cluster with `talosctl health`
- [ ] **pfSense:** recover WebGUI/PHP-FPM and require authenticated
- [ ] **Prometheus:** configure `HOMELAB_PROMETHEUS_URL` in the authoritative
- [ ] **Sentry:** prove a bounded synthetic event ID and downstream ingestion;
- [ ] **Pyroscope:** identify a real readiness endpoint and prove recent profile
- [ ] Add workstation-vs-TrueNAS diagnostics for pfSense and Prometheus without
- [ ] Re-run `scripts/diagnose-local-runtime-dependencies.py` and require every
- [ ] Resume TrueNAS NFS/Kubernetes CSI acceptance after this gate converges.

## P0 — appliance protection and health latency

- [ ] Measure a safe TrueNAS/pfSense probe envelope: origin rate, concurrency,
- [ ] Attribute remaining cold-path cost in `/api/homelab/health`; keep provider
- [ ] Prove appliance degradation cannot exhaust FastAPI workers or create probe
- [ ] Validate the 2.5 s protection threshold against measured p95/p99
- [ ] Collect a sustained TrueNAS-runtime baseline and correlate p95/p99,
- [ ] Correlate bounded pfSense nginx/pfREST evidence with the passive
- [ ] Implement the bounded generated-nginx/pfREST log capture in
- [ ] Reconcile the latent `nabla-compose/apps/crowdsec/compose.yml`
- [ ] After an independent pfSense observer path is accepted, expand the
- [ ] Improve TrueNAS WebSocket timeout attribution without leaking URI or

## P0 — canonical Nabla catalog cutover

- [ ] Fix `nabla-compose/catalog/services.schema.json` so `internalUrl` matches
- [ ] Replace service-id/display-name joins and three-way drift checks with
- [ ] Consume authoritative BIA-derived business criticality beside
- [ ] Remove `homelab-services.json` and `homelab-exposure-overrides.json` as
- [ ] Pin rollback evidence and validate stable entity refs, relation endpoints,
- [ ] Add an explicit catalog revision/provenance field so deployed runtime,

## P0 — deterministic offline agent validation

- [ ] **Exact-HEAD materialization:** acquire the approved commit SHA through a
- [ ] **Run gates against the same source tree:** execute `bash -n`, targeted
- [ ] **Preserve security coverage:** keep SAST and BetterLeaks in the canonical
- [ ] **Bound agent transcripts, not evidence:** display concise failing
- [ ] **Publication acceptance:** attach a concise validation matrix to the PR

## P1 — dependency automation and CI governance

- [ ] Introduce **Dagger CI** as the portable local-first execution layer, not as
- [ ] Benchmark native baseline and Dagger against the same SHA,
- [ ] Pin the Dagger CLI/Engine and initialize a Python SDK module; the
- [ ] Model the deterministic local gates first: targeted/full pytest, Ruff
- [ ] Make the existing exact-HEAD archive/snapshot materialization usable as
- [ ] Expose the same Dagger functions through `just` locally and a thin
- [ ] Keep production credentials out of cacheable Dagger layers and pass
- [ ] Accept the pilot only when the same SHA produces equivalent local and CI
- [ ] Validate the hosted Mend Renovate GitHub App for this repository and
- [ ] After acceptance, remove the self-hosted Renovate workflow.
- [ ] If CVE ownership moves to Renovate, prove Dependabot Alert reconciliation
- [ ] Re-enable selective automerge only when required checks are authoritative
- [ ] Validate master-red remediation with one controlled non-production drill.
- [ ] Review the first successful post-deployment ZAP artifacts and suppress only
- [ ] Residual: `vercel@64.5.0` (latest) still pins `smol-toml` `1.5.2`
- [ ] Residual: the blocking scope still skips `uv.lock`/`Pipfile.lock` and
- [ ] `diskcache` (GHSA-w8v5-vhqr-4h9v) and `git-url-parse`
- [ ] Residual: `uv.lock` remains in `--skip-files` of
- [ ] Residual: Starlette 1.8 warns that `starlette.testclient` with
- [ ] Residual: the image scan in `docker-build.yml` (Trivy action `v0.71.2`,
- [ ] Residual: MegaLinter `v10.0.0` bundles its own Trivy and downloads the
- [ ] Protect `master` with reviewed PRs and final required checks once normal CI
- [ ] Decide whether merge-candidate `[skip ci]` must then be prohibited.

## P1 — release and deployment

- [ ] Trigger FastAPI Cloud deployment from the existing
- [ ] Deploy immutable release tags instead of a moving branch.
- [ ] Consolidate push/release rollout after the repaired release sequence is
- [ ] Publish images with semantic-version and commit-SHA tags, signed provenance
- [ ] Keep generated SBOMs as artifacts rather than tracked large files.
- [ ] Disconnect the Git provider from the Vercel project with an authorized
- [ ] Prove a later PR push creates no Vercel deployment, status or comment.

## P1 — dual-vantage probes and code reduction

- [ ] Prove `HOMELAB_PROMETHEUS_URL=http://172.17.0.24:9090` on the TrueNAS
- [ ] Keep all outside-in public probes embedded in FastAPI Cloud unless another
- [ ] Reduce the external Python probe implementation with mature libraries
- [ ] evaluate the same AnyIO transport primitives for the specialized
- [ ] Evaluate **Synthetic Open Schema (SOS)** as a generated contract, not as a
- [ ] Move public exposure intent from transitional
- [ ] Validate every generated resource with the official
- [ ] Measure deletion after a runner-adapter POC. Current minimum candidate
- [ ] Adopt the runner only if the net production/test LOC and maintenance
- [ ] Do not adopt young all-in-one libraries such as PyUptimeKit/pyhealthcheck
- [ ] After internal delegation is proven, delete only the TrueNAS/internal
- [ ] Residual: vendored cookiecutter hooks `ccds/hook_utils/configure_gh.py`
- [ ] Prove the GNU branch of those shell fallbacks on the Linux CI runner:

## P1 — runtime architecture

- [ ] Residual: deployed acceptance proof. Acceptance: after deployment,
- [ ] Residual: Sentry initialises `target=cloud` on the workstation, so dev
- [ ] Residual: gunicorn `--reload` (`make up`) logs `Worker reloading`
- [ ] Residual: on this workstation `/healthz` took ~8 s without
- [ ] Residual: importing the factory still imports `nabla.api`, which builds
- [ ] Residual: the minimal app's `/api/runtime/topology` still calls
- [ ] Residual: `/healthz` and the health-board
- [ ] Residual: no environment switch selects features for `nabla.main:app`
- [ ] Residual: live LAN acceptance of the minimal app against homelab
- [ ] Move remaining global DB/Redis resources behind lifecycle/state or injected
- [ ] Consolidate SQLAlchemy/`databases`/psycopg lifecycle and move schema
- [ ] Split dependency groups into runtime/observability/homelab/AI/dev boundaries
- [ ] Replace the Git-tagged TrueNAS client dependency with an immutable commit or
- [ ] Create lifespan-owned shared `httpx.AsyncClient` pools with explicit
- [ ] Keep unit tests hermetic; perform LAN acceptance only through explicit

## P2 — application/domain backlog

- [ ] **Notes contract normalization**: inventory current API models, database
- [ ] Residual — production/staging rollout: before `alembic upgrade head`,
- [ ] Residual — real databases: on each deployment check
- [ ] Residual — offline `alembic upgrade head --sql` is unsupported (both
- [ ] Residual — run `-m integration` (Alembic + Notes) in CI with a
- [ ] Residual — note ownership: add an owner column and 403 semantics only
- [ ] Residual — browser + PostgreSQL acceptance of list/add/edit/toggle/
- [ ] Residual — a stored row violating `NoteResponse` constraints makes
- [ ] Residual — `POST /notes/add` hard-codes `description`/`type`/`prompt`
- [ ] **RAG concurrency and persistence**: replace global mutable vector state
- [ ] Test concurrent indexing/search, lifecycle shutdown, persistence across
- [ ] Keep failures in the optional RAG backend out of core app liveness.
- [ ] **SearXNG integration**: first establish the authoritative Compose service
- [ ] **MCP SDK and pfSense**: pin/review SDK API changes; retain private
- [ ] **Compose/Docker consolidation**: current references indicate
- [ ] Audit references across Makefile, justfile, mise, Helm and workflows.
- [ ] Build/smoke canonical `Dockerfile` + `docker-compose.yaml` locally.
- [ ] Remove obsolete files only after reference and rollback checks pass.
- [ ] **P2 merge evidence**: for every changed contract, record targeted test,
