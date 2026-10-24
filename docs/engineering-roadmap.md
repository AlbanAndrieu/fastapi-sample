# Engineering roadmap — active, acceptance-driven

**Version : 2026-10-24.** Keep only unresolved deliverables and validation
conditions here. Do not append completed PR narratives.
For long-tail unchecked tasks use the [on-demand backlog](engineering-backlog.md);
it is **not** an automatically approved roadmap. Historical implementation
notes remain in [Git history](https://github.com/AlbanAndrieu/fastapi-sample/blob/594d51d64efdd5274d2ba42a9cb09551b6d57d46/docs/engineering-roadmap.md).

## P0 — Contrat de convergence Compose / FastAPI / Site (24 octobre 2026)

- [x] Indexer l'[analyse commune du site](https://github.com/AlbanAndrieu/nabla-site-alban/blob/feat/catalog-icon-source-convergence-20261024/docs/homelab-catalog-convergence-2026-10-24.md) dans la PR #373 ; ne pas recopier les 151 identités Backstage, les 176 noms de fichiers d'icônes ou les relations dans le backend.
- [x] La projection SERVICE ne contient que `entityRef`, état expurgé et `catalogRevision` corrélé ; toute identité ambiguë ou observation absente reste `unknown`. Les données d'exploitation appartiennent aux DTO OWNER et aux collecteurs FastAPI.
- [ ] Définir un DTO OWNER versionné **par preuve et `entityRef`** avec la source, la fraîcheur, `observed_at`, le résultat, la latence si mesurée et une raison bornée : runtime principal TrueNAS/Docker, DNS, TCP, TLS, HTTP/API, Cloudflare, Gatus, Prometheus et exporters. Ne pas publier ce DTO via SERVICE ou le cache navigateur.
- [ ] Vérifier depuis un collecteur LAN autorisé les 85 adresses LAN déclarées et la couverture actuelle `internal_probes_enabled=false` (0/86 sondées), sans activer des sondes LAN depuis le cloud ni confondre déclaration et observation.
- [ ] Réconcilier les ports déclarés et observés pour Gatus, Bichon, Garage Web UI et Garage Admin avec Compose/TrueNAS avant toute modification d'URL exposée ; distinguer 302 Access de la santé de l'origine. Consolider 11 dérives Cloudflare et 12 origines protégées non vérifiées, selon leur identité canonique.
- [ ] Mesurer la couverture 16/28 WAN (rotation 12/cycle), la fraîcheur des preuves et le cas `prometheus` application RUNNING / conteneur principal exited sur trois nouveaux relevés ; ne pas transformer un historique en statut courant.
- [ ] Prouver la parité sur le même `catalogRevision` avec la PR site #254, puis exécuter les tests, `just p0`, `just quality` en local et contrôler le backend réellement déployé. Aucune CI payante ni déploiement implicite.


## P0 — Réconcilier les états TrueNAS/Docker et la couverture réelle (24 octobre 2026)

- [x] Diagnostic documenté depuis l'observation OWNER du 24 octobre : 95 applications (81 RUNNING, 13 STOPPED, 1 DEPLOYING), 88 services, 0 résultat `internal_services` lorsque `internal_probes_enabled=false`. Les champs `exposure.declared.internal_host/internal_port` restent disponibles pour 85 services, sans être des résultats de sonde.
- [x] Détecter le cas Prometheus : application TrueNAS `RUNNING`, mais conteneur principal `prometheus` à `exited`. Exporter `runtime_primary_container_state` et `runtime_primary_container_issue` par service et rétrograder la santé `ok` en `warn` si la preuve principale récente contredit l'application. Ignorer les conteneurs init/migration terminés normalement ; ne pas conclure lorsque la correspondance est ambiguë.
- [x] Ajouter des tests Python sur conteneur principal arrêté, sidecar init, ambiguïté et instantané runtime périmé.
- [ ] Valider le vrai provider TrueNAS et les résultats depuis le LAN sur au moins trois relevés distincts. Ne pas modifier les conteneurs ni démarrer de sondes dangereuses depuis FastAPI Cloud.
- [ ] Vérifier les 28 services éligibles aux sondes publiques, les 16 preuves connues (57,1 %), la rotation 12/cycle, les 3 preuves mémoire et le niveau de fraîcheur. Distinguer HTTP 302 de Cloudflare Access (edge atteinte) et preuve d'origine réellement joignable.
- [ ] Ajouter un contrat de métriques par `entityRef` pour Prometheus/Gatus/exporters : état de scrape, âge, dernière valeur, provenance et erreurs. Aucun green sur simple présence d'un processus exporter.
- [ ] Étudier l'activation de sondes LAN **depuis un agent LAN autorisé**, sans rendre accessibles des IP privées depuis FastAPI Cloud ; séparer la collecte et sa publication OWNER.
- [ ] Exécuter `pytest tests/unit/test_homelab_service_health.py`, `just offline-l1`, `just p0`, `just quality` sur le HEAD exact. Tester la Preview site #254 et le backend déployé seulement après validation ; aucune CI payante ni déploiement automatique.

## P0 — Contrat SERVICE Backstage v2 partagé avec Site Alban (2026-10-24)

- [x] `nabla-compose/catalog/generated/entities.json` reste la source des identités déclarées. Audit actuel : 154 entités (128 Component, 23 Resource, 1 Domain, 1 Group, 1 System) ; les 151 Component/Resource/API ont une correspondance d'icône dans les 176 `webAssets` de Compose. Le site génère ses chemins d'icônes localement et ne doit pas les recopier dans le DTO FastAPI.
- [x] Projeter la santé par `entityRef` sans réutiliser une seule observation identifiée par `metadata.name` lorsque ce nom désigne plusieurs entités Backstage : toutes les correspondances ambiguës retournent `unknown`, jamais un état `ok` supposé. Correction et test dans la PR #373.
- [ ] Exécuter les tests existants de `tests/unit/test_site_health_v2.py`, les tests des vues publiques et la quality gate locale au HEAD exact, sans GitHub Actions. La reproduction ciblée de la correction a passé 3/3 tests en environnement isolé ; la suite complète reste NON EXÉCUTÉE.
- [ ] Vérifier la parité `catalogRevision` et `entityRef` avec la PR site #254 en Preview exact-SHA, pour les 151 entités canoniques. Si une observation est inconnue, l'afficher `unknown`, sans inventer de sonde ou de relation.
- [ ] Retirer les accès temporaires `HOMELAB_PUBLIC_DIAGNOSTICS_READONLY` après validation MFA/VPN. Conserver le SERVICE public expurgé indépendant des diagnostics OWNER.

## P0 — Réconciliation FastAPI / Site Alban / Compose : données LAN du 24 octobre 2026

- [ ] **Installation volontaire du skill Vercel par le propriétaire** : me demander explicitement d'exécuter moi-même `npx skills use "https://github.com/vercel-labs/agent-skills" --skill "web-design-guidelines"` depuis mon poste lorsque l'accès npm sera disponible. L'agent ne doit pas installer ce skill automatiquement. Après installation, consulter la sortie complète et le répertoire `supporting-files` annoncé avant une nouvelle revue UI.
- [ ] **Aligner les cibles Compose (`catalog/homelab-services.json`) sur les preuves LAN** : Gatus UI `172.17.0.24:8085`, Bichon UI `:15630`, Garage S3 API `:3900`, Garage Admin API `:3903`, Garage Web UI `:3909`. Conserver Traefik proxy TLS `:443` et identifier séparément sa Dashboard UI `:8080`. Supprimer les ports historiques `30287`/`30313` après contrôle des générateurs. Aucune configuration Cloudflare ne doit être présumée modifiée.
- [ ] **Normaliser les ID canoniques sans modifier les noms de conteneurs ni DNS** : `homeassistant` et `openwebui` sont les clés ; maintenir les alias de lecture `home-assistant`/`open-webui` uniquement pour les catalogues historiques. Suffixer les noms visibles par rôle (UI, API, MCP), sans transformer les services S3/REST en liens de navigateur ni dupliquer les entités.
- [ ] **Amont Compose** : aucune PR ouverte dans `AlbanAndrieu/nabla-compose` au début de cette correction ; reporter les mutations de la source canonique dans une PR Compose autorisée, plutôt que d'écrire directement sur `master`. Les corrections locales de consommation restent transitoires tant que l'autorité n'est pas corrigée.



- [x] **Classifier les anomalies observées** : échantillon v6 horodaté du 24/10 à 13:08Z (non temps réel) : 88 services, 28 déclarés publics, 48 `exposure.state=mismatch`, 65 `risk_state=at_risk` (catégories pouvant se chevaucher), 37 tunnels observés pour des services déclarés internes, 26 incohérences de token Service Auth, 7 applications Access attendues non observées, 11 origines Cloudflare différentes des endpoints déclarés, 12 origines protégées non vérifiées, 86 cibles LAN éligibles mais 0 sondée (`internal_probes_enabled=false`). Le tableau global était `stale` (164 secondes) tandis que certaines preuves étaient récentes. Ne pas convertir ces catégories en incidents confirmés sans preuve de configuration effective.
- [ ] **P0 routage et sécurité** : vérifier dans `nabla-compose` le port publié, le port interne et les règles Proxy/Access avant de corriger les divergences observées : Garage Web UI, Garage Admin API, Gatus, Bichon, DDNS Updater, AnythingLLM workstation, LiteLLM workstation, Ollama GPU, Speedtest, Stirling workstation et Traefik. Ces 11 différences ne prouvent pas à elles seules une panne ; priorité aux surfaces d'administration et aux routes qui changent de rôle.
- [ ] **P0 Cloudflare Access** : les réponses 302/403 d'Access prouvent la présence du bord, pas le succès de l'origine. Examiner la configuration du token Service Auth propre au projet et les dérogations déclarées. Vérifier particulièrement la politique path-level `bypass` signalée pour n8n ; ne pas modifier les règles sans preuves et validation du périmètre.
- [ ] **P0 identité et runtime** : comparer `catalogRevision` et `entityRef` de `nabla-compose`, DTO SERVICE FastAPI et Site #254. Ne jamais attribuer une mesure à deux entités homonymes ; produire `unknown` si l'identité est ambiguë. Signaler séparément `app.RUNNING` et `runtime_primary_container_state=exited` (constaté pour Prometheus).
- [ ] **P0 couverture et confidentialité** : compléter une collecte LAN depuis un observateur explicitement autorisé, sans utiliser FastAPI Cloud comme source d'accès au réseau interne par défaut. Garder les IP/ports et sondes OWNER hors du DTO public, du cache navigateur partagé et de la réponse hors Wi-Fi. Distinguer `origin`, `memory`, `last_success_at`, `stale` et `not_sampled` ; tester la parité avec le site #254.
- [ ] **P1 performance** : mesurer la liste supérieure à 50 cartes (pagination ou `content-visibility` sous validation navigateur), les coûts de rendu ReactFlow et les changements de layout à 320/360/390/768/1280 px.

## P0 — Audit Vercel Web Interface Guidelines appliqué à la UI

- [x] **Instructions skill** : `npx skills use` tenté dans l'agent avec sortie capturée ; `EAI_AGAIN registry.npmjs.org`, aucun `supporting-files` fourni. Instructions originales lues via `vercel-labs/agent-skills/skills/web-design-guidelines/SKILL.md` et règles fraîches via `vercel-labs/web-interface-guidelines/command.md`. Aucune installation ni dépendance ajoutée.
- [x] **Correctifs UI** : création des contrôles avancés avant la barre globale sur session détaillée, libellés stables et états `aria-pressed`, menu `aria-controls`/`aria-expanded` avec contenu `hidden`, champ de recherche `name` et libellé, raccourci `/` qui dévoile d'abord le champ, choix d'ouverture respecté après scroll tactile, Reset sans focus forcé sur contenu caché, hover/focus, `touch-action`, safe areas, compteurs tabulaires et message d'état vide.
- [x] **Contrôles ciblés** : parsing JavaScript des deux modules et 18 assertions de comportement simulées PASS ; tests de contrat Python ajoutés pour être exécutés sur checkout complet.
- [ ] **À valider avant Ready/merge** : navigateur réel tactile + clavier/screen reader, zoom 200 %, absence de débordement, fonctionnement des 11 sondes réelles, `pytest` ciblé, `just offline-l1`, `just p0`, `just quality` sur HEAD exact. **NOT_RUN** dans cet agent : checkout complet et npm indisponibles. Aucun déploiement ni GitHub Actions.

## P0 — Incident FastAPI Cloud : UI vide et faux besoin de connexion OWNER (2026-10-23)

- [x] Diagnostiquer les deux causes indépendantes : le bootstrap du navigateur bloquait le health board sur `ownerSessionAvailable()`, et `/api/ui/services` échouait sans repli lorsque `catalog/generated/entities.json` (Backstage v2) était indisponible.
- [x] **Rollback temporaire approuvé** (#370) : `HOMELAB_PUBLIC_DIAGNOSTICS_READONLY=true` (défaut temporaire) rétablit uniquement les lectures GET/HEAD explicitement autorisées : health board, sondes TrueNAS/DNS/TCP/API, pfSense, Cloudflare, topologie et télémétrie. Un lecteur anonyme reste `authenticated=false` ; aucun cookie OWNER implicite, purge de cache, POST ni endpoint admin/MCP/metrics autorisés. **Exposition publique potentielle d'IP/ports/topologie : à retirer dès l'accès privé validé.**
- [x] En absence du catalogue Backstage, réutiliser le **snapshot déjà empaqueté et validé** du homelab (pas un nouveau catalogue concurrent). Publier seulement les libellés sûrs et, lorsque le cache partagé est réellement `fresh` et la correspondance ID non ambiguë, les états `ok/warn/fail`. Sinon `unknown` ; provenance explicite `catalogSource=bootstrap-snapshot` et `boardState`. Pas d'adresse IP, de port, de secret ou d'URL interne. Limiter les tentatives Backstage après échec à une par 60 secondes.
- [x] Distinguer les bascules : `HOMELAB_UI_PUBLIC_READONLY_ENABLED` gère le répertoire expurgé ; `HOMELAB_PUBLIC_DIAGNOSTICS_READONLY` ouvre temporairement une liste fermée de lectures détaillées. Les actions ADMIN/MCP et les écritures restent protégées. En lecture anonyme, `?refresh=true` ne doit jamais forcer les sondes.
- [x] **Diagnostic UI consolidée (#370/#373)** : cartes et preuves des 11 contrôles, flux TrueNAS DNS → TCP → TLS → HTTP/API → métriques, source et durée quand mesurées. Pas de résultat implicite lorsqu'une preuve manque.
- [x] **Filtrage mobile compact (#373)** : icône et compteur par état (Tous, Operational, At risk, Degraded, Down, Unknown), bascule on/off accessible via `aria-pressed`, raccourcis protocoles et recherche repliés en mode compact. Les contrôles existants restent la source de vérité ; sélection synchronisée avec l'URL et les filtres avancés. Libellés révélés au survol, au focus et pendant l'appui tactile ; libellés accessibles conservés.
- [ ] **Validation UX exacte révision** : 320/360/390/768/1280 px, orientation et zoom 200 %, clavier, TalkBack/VoiceOver, survol/toucher, historique arrière/avant, zéro service, statut inconnu, latences et sondes retardées. Vérifier l'absence de débordement et que les labels restent disponibles sans hover.
- [x] **Sélection du skill UI** : choisir `vercel-labs/agent-skills/web-design-guidelines` comme unique skill général d'audit de la page HTML/CSS/JavaScript. Critères : compatibilité avec le rendu existant, accessibilité WCAG, qualité des prescriptions, maintenance, adoption et supply-chain. Anthropic frontend-design et UI/UX Pro Max sont des alternatives pour une refonte esthétique, pas nécessaires ici ; PracticalSwan est pertinent mais peu adopté ; Anthropic Design System reste facultatif pour les tokens. Chiffres Skills.sh observés le 2026-10-24, indicatifs, sans installation automatique.
- [x] **Application des patterns Visa et W3C dans #373** : barre mobile de filtres de statut à icônes et compteurs ; noms accessibles constants et compteurs décrits séparément ; `aria-pressed`, `aria-controls` et `aria-expanded` ; volet avancé réellement masqué lorsque fermé ; Reset visible pour les filtres actifs ; chips actifs conservés, et message d'absence de résultat. Réutiliser les `select` existants et synchroniser l'URL.
- [ ] **Contrôle design system** : inspecter les tokens CSS, simplifier les overrides concurrents, vérifier contraste, cibles tactiles 44 px et clavier. Tester les aides au survol, focus et toucher sans y cacher une information essentielle.
- [ ] **Échantillon LAN pour parité diagnostique** : données utilisateur du 2026-10-24T13:08:36Z : 88 services, 27 ok, 24 warn, 14 fail, 23 unknown ; 11 sondes origine, 3 sondes mémoire et aucune sonde interne rapportée ; health board stale au moment de la capture. Afficher séparément runtime Docker, disponibilité de l'origine, route Cloudflare, source, horodatage et latence. Un état RUNNING ou une redirection 302 d'Access ne prouve pas la disponibilité applicative. Examiner ensuite les écarts Garage/Gatus et les politiques Access en source, sans republier les IP/ports privés dans le catalogue public.

- [ ] **P0 de validation production** : FastAPI Cloud se déploie directement hors GitHub Actions. Identifier la révision réellement déployée et promouvoir la correction par la procédure de déploiement **explicitement approuvée**. Le merge GitHub seul ne prouve pas que `https://fastapi-sample.fastapicloud.dev/api` est actualisé.
- [ ] Contrôler depuis le réseau mobile externe et Wi-Fi maison : `/api` sans `Sign in` ni `Owner only`, cartes détaillées + DNS/TCP/API/WebSocket/Cloudflare/pfSense/TrueNAS, `/api/topology` et `/api/topology-telemetry` 200, `/api/homelab/probes` 200 ; `GET /api/ui/session` retourne `authenticated=false` + `readOnlyDiagnostics=true` ; cache reset POST et `/admin`, `/metrics`, `/mcp` protégés. Vérifier les sondes réellement confirmées sans convertir les trous de couverture en `GREEN`.
- [ ] **Rétablir OWNER** après mise en place MFA/VPN/proxy d'identité : définir `HOMELAB_PUBLIC_DIAGNOSTICS_READONLY=false`, conserver un catalogue expurgé accessible sans connexion et confirmer le retour de 401/403 sur les routes détaillées. La bascule distincte `HOMELAB_UI_PUBLIC_READONLY_ENABLED` pilote uniquement le répertoire minimal ; ne pas les confondre. Audit de divulgation obligatoire.
- [ ] Exécuter gates locales exact HEAD : pytest ciblé du dépôt, `just offline-l1`, `just p0`, `just quality`, tests navigateur et contrat anti-divulgation ; CI GitHub interdite pendant la pénurie de crédits. Les 11 tests Python du module isolé vérifié par SHA Git et les tests JavaScript simulés passent, mais les gates du dépôt restent **NOT_RUN**.
- [x] Gate locale au HEAD `09507f63` : repli Backstage cassé (`_bootstrap_public_service_directory()` appelé sans `request` ⇒ `TypeError`/500 à la première panne) corrigé ; contrats `python.yml` (6 gardes Draft depuis #365) et ordre `installHealthUiFinalFollowup` réalignés ; C901/PLC0415/PLW0603 soldés.
- [ ] **NOT_RUN** : `just offline-l1`, `just p0`, tests navigateur (node@24.22.1 absent localement ; `mise.lock` non rafraîchi volontairement, à faire via `mise lock` depuis une source de confiance). Les 23 commits portent `[skip ci]`, désormais interdit par AGENTS.md : vérifier que les checks requis démarrent au passage Ready.

## P0 — Bababou local-first parity and Talos staging (PR #365, 2026-10-22)

- [x] Remove both obsolete GitHub workflows `deploy.yml` (FastAPI Cloud deploys independently) and manual Super-Linter `linter.yml`; preserve Python, CodeQL, security scans, MegaLinter, artifact and package release gates. Remove stale MegaLinter exclusion.
- [x] Port the **concepts**, not the Node/npm implementation, of Bababou #238: `just offline-l1` validates changed Python AST, Shell and strict JSON without dependency resolution; `just p0` adds targeted Python contracts using already-installed dependencies; `just workflow-audit` continues to use pinned actionlint/zizmor.
- [x] All three pull-request workflows enforce explicit job-level draft guards and `ready_for_review`; `scripts/ci/check_draft_workflows.py` and its negative tests fail closed on an unguarded runnable job. This saves runner minutes in Draft without suppressing future required security checks.
- [x] Provide opt-in, non-public Talos/Kubernetes staging manifests, Kustomize, in-cluster readiness probes, resources, NetworkPolicy, required out-of-band Secret and regression contracts in `deploy/talos/`. Unverified image digest blocks accidental deployment.
- [ ] Execute `just offline-l1`, `just p0`, `just workflow-audit`, `just quality` and `just publish-check` against a **complete local checkout of exact HEAD**; if GitHub DNS or toolchain remains unavailable, status is NOT_RUN, never PASS.
- [ ] On actual Talos, validate secret provisioning, approved image digest and CNI/Traefik allowlist, plus owner-CIDR provenance and signed identity before opening any private Ingress. Preserve cloud outside-in probing; no production cutover without separate approval.

## P0 — Temporary OWNER access from outside home network (2026-10-22)

- [x] Temporary opt-out of the **source-CIDR requirement only**: `HOMELAB_OWNER_REMOTE_ACCESS_ENABLED=true` (temporary default) permits a remote browser to unlock diagnostics using `DIAGNOSTICS_ACCESS_KEY` and a 20-minute signed HttpOnly cookie. Signed Cloudflare owner JWT remains mandatory where used. Exception temporaire (#370) : certaines lectures de diagnostics et sondes sont publiques lorsque `HOMELAB_PUBLIC_DIAGNOSTICS_READONLY=true` ; métriques brutes, ADMIN, MCP et écritures restent protégées.
- [x] Keep origin/CSRF checks and the existing site API SERVICE machine key. No credential in URL, HTML, localStorage, Git or browser requests to the site. Document clearly that a source IP is no longer a required factor **while this switch is true**.
- [ ] **Restore OWNER defense-in-depth**: set `HOMELAB_OWNER_REMOTE_ACCESS_ENABLED=false` after a verified remote Cloudflare Access MFA/operator session or VPN/identity-aware proxy is available; verify 401 without key, 403 outside trusted CIDR, read/write separation, 20-minute expiry and same-origin restrictions. Target: next secure remote-access cutover, do not leave this permanently enabled.
- [ ] End-to-end check on the actually deployed revision (external/mobile vs home): signed login, FastAPI board data, /api/service overview, site Backstage v2 catalogue, private APIs still denied. Tests and production deployment on this PR remain **NOT_RUN**.

## P0 — UI FastAPI Cloud accessible hors domicile (23 octobre 2026)

- [x] Retirer les placeholders `Owner only` des cinq cartes de synthèse de `/api` pour les visiteurs non authentifiés. Utiliser exclusivement `GET /api/ui/services` (projection Backstage v2 explicitement publique : noms validés, catégorie et état `ok/warn/fail/unknown`) pour afficher le répertoire complet et cinq compteurs cohérents.
- [x] Les absences de snapshot, les erreurs de catalogue et les réponses périmées n'affirment jamais qu'un service est sain : compteur `UNKNOWN` ou `Unavailable`. Aucun champ d'adresse privée, URL interne, port, clé, diagnostic brut ni topologie n'est repris de `/healthz` ou `/sickz` dans le flux public.
- [x] Ne plus traiter l'absence normale de session OWNER comme une panne de la page : préciser que seul le détail des sondes et le contrôle opérateur requièrent une authentification.
- [ ] Vérifier le *déploiement FastAPI Cloud direct* et `/v2/version` contre le HEAD : les commits dans GitHub ne garantissent pas la mise à jour de `fastapi-sample.fastapicloud.dev`. Ne pas déclencher de job GitHub Actions ni de `fastapi deploy` depuis l'agent.
- [ ] Depuis un client mobile en 4G/5G et depuis le Wi-Fi domicile : `/api/ui/services` HTTP 200 avec liste ; `/api` affiche la même liste et les compteurs ; aucun `Owner only` dans les résumés ; états périmés `UNKNOWN`. Vérifier séparément session OWNER 401 sans clé, clé invalide 401, clé valide 200, origine invalide 403.
- [ ] Après une solution distante authentifiée MFA/VPN validée : remettre `HOMELAB_OWNER_REMOTE_ACCESS_ENABLED=false`, et désactiver le répertoire public avec `HOMELAB_UI_PUBLIC_SERVICES_ENABLED=false` **seulement si** un remplaçant externe authentifié garantit la disponibilité attendue. Réévaluer la divulgation volontaire des libellés de services.
- [ ] Contrôles locaux sur un checkout complet exact HEAD : `just offline-l1`, `just p0`, `just quality` et tests navigateur ; sans accès au clone, statut **NOT_RUN** plutôt que PASS.

## P0 — FastAPI Cloud Python : dernière version disponible et compatibilité (23 octobre 2026)

- [x] Vérification des **documents officiels FastAPI Cloud** : toutes les branches Python actuellement prises en charge (3.10+) sont annoncées, la dernière stable disponible étant **3.15.1** au 21 octobre 2026. La disponibilité exacte de cette révision dans le builder Cloud et le runtime actuel de l'application déployée n'ont **pas pu être vérifiés** par l'agent.
- [x] Remplacer le helper historique `scripts/truenas/run-pr350-tests.sh` (PR #350 déjà fusionnée) et son test unitaire spécifique par `just offline-l1`, `just p0`, `just quality` et `just publish-check`. Conserver uniquement l'incident exploitable de `/tmp noexec` dans le runbook TrueNAS.
- [x] Ajouter `just python-cloud-audit` : lecture sans réseau de `pyproject.toml` et `uv.lock`, état `BLOCKED_PENDING_RESOLUTION` pour 3.14.9 ou 3.15.1, nombre de distributions natives dépendantes de l'ABI 3.13. `just python-cloud-probe` lance un `uv lock --dry-run` **hors du dépôt** et **hors réseau par défaut**, avec Python candidat déjà présent ; jamais de changement de verrou produit ni de déploiement.
- [ ] Tester la **cible de migration 3.14.9** : `python scripts/ci/check_fastapi_cloud_python_upgrade.py --candidate 3.14.9 --probe --allow-network` sur une machine isolée/connectée avec un uv et un Python 3.14.9 de confiance, résoudre proprement tout le graphe et obtenir une révision `uv.lock` complète. Vérifier le nombre de wheels Linux x86_64, les dépendances `pyroscope-io`, `pysqlite3`, `ddtrace`, `truenas-api-client`, ainsi que tous les groupes activés.
- [ ] Exécuter les tests ciblés, l'ensemble des quality gates locales, les tests Docker et les smoke tests FastAPI Cloud/TrueNAS sur la révision exacte, sans déclencher GitHub Actions. Seulement après succès, aligner **ensemble** `requires-python`, `uv.lock`, `.python-version`, `mise.toml`, Docker et version de build Cloud. Ne pas publier Python 3.15.1 sans refaire cette procédure.
- [ ] Lorsque la production sera accessible, établir de façon sûre sa version Python (preuve côté serveur, sans révéler de secrets dans la UI) et comparer à la cible ; la documentation du fournisseur ne constitue pas une preuve de déploiement.

## P0 — Toolchains supportés et LTS (23 octobre 2026)

- [x] Fixer **Node.js 24.22.1 LTS** (21 octobre 2026, correctifs de sécurité) dans `mise.toml` et le fallback `.envrc`. Les workflows lisent Node depuis mise : ne pas dupliquer de numéros de version.
- [x] Appliquer **Python 3.13.17** sur les outils développeur, dans le cadre du `uv.lock` existant (`requires-python = "==3.13.*"`). Python ne propose pas de branche officiellement appelée LTS ; 3.13 reste maintenue pour la sécurité jusqu'en octobre 2029. L'image `python:3.13-slim-trixie` prend les correctifs de la série lors des reconstructions.
- [x] Régénérer et vérifier `mise.lock` sur une machine connectée (23 octobre 2026) : `mise lock`/`mise install` ont produit les entrées Node 24.22.1, Python 3.13.17 et uv ; les 6 checksums linux-x64/macos-arm64 sont **identiques** aux sommes officielles publiées (`nodejs.org/dist/v24.22.1/SHASUMS256.txt`, `SHA256SUMS` de la release python-build-standalone `20261021`, `.sha256` des assets uv 0.12.22). `.python-version` 3.13.17, Node v24.22.1, npm 12.2.0, uv 0.12.22 concordent.
- [x] uv figé à **0.12.22** dans `mise.toml` (même version que `setup-uv` de `python.yml`, au lieu de `latest` verrouillé en 0.12.6) : le backend pypi de mise (ex. `azure-cli` déclaré globalement) exige uv ≥ 0.12.10 et échouait dans ce dépôt. L'archive linux-x64 d'uv passe de musl à gnu (images Debian slim, mise non utilisé dans Docker/CI).
- [x] `engines.node` `>=26` (vestige de #343, quand `mise.toml` épinglait Node 26) aligné sur `>=24.22.1` dans `package.json` et `package-lock.json` ; `npm ci --dry-run` sous Node 24.22.1 : 0 `EBADENGINE`. `release.yml` passe d'uv `0.12.1` à `0.12.22` ; `test_uv_version_matches_across_mise_and_workflows` impose désormais la même version d'uv dans `mise.toml`, `python.yml` et `release.yml`.
- [ ] **NOT_RUN** : prochain run réel de `release.yml` (déclenché par une release) avec uv 0.12.22.
- [ ] Qualification de **Python 3.14.9** (maintenu jusqu'en 2030) : régénérer intégralement le verrou `uv.lock` via `uv lock`, auditer les wheels Linux amd64, `pyroscope-io`, `pysqlite3`, `truenas-api-client`, FastAPI/ASGI et tous les groupes `uv`; exécuter tests, image Docker et acceptation Talos avant d'assouplir `requires-python ==3.13.*`. Ne jamais modifier manuellement `uv.lock` ni publier une image 3.14 sans résolution valide.
- [ ] Gates locales de l'exact HEAD : `just offline-l1`, `just p0`, `just workflow-audit`, `just quality`, tests Docker. Aucun GitHub Actions payant ni déploiement déclenché par l'agent.

## P0 — CI : tracker unique `master-red` (#355)

- **Implémenté, à valider** : un seul commentaire d'état du bot dans #355, sans nouvelle issue par SHA, sans PR brouillon vide, sans modification du titre, du corps ni des labels ; conservation des preuves des 32 anciens doublons dans GitHub. Script canonique : `scripts/ci/master_red_issue.py`.
- **Protection humaine** : une modification manuelle du titre, du corps, des labels, de l'état **ou un commentaire humain avant/après inscription** interdit toute mutation automatique future. #355 a été renommée manuellement : elle ne doit jamais être clôturée/réouverte par le bot, même après deux succès. Seule une issue sans intervention humaine peut bénéficier de la clôture après deux numéros de runs `master` consécutifs tous verts.
- [ ] Exécuter `python3 -m unittest tests.unit.test_master_red_issue -v` sur le HEAD exact et la gate locale ; aucune preuve de réussite CI globale à inférer.
- [ ] Après déploiement sur `master`, constater deux runs complets consécutifs (CodeQL/ZAP `skipped` acceptables **uniquement** si non requis par la classification), et vérifier les causes racines Python/Smoke. Ne pas provoquer d'échec artificiel.

## P0 — FastAPI Cloud owner UI and catalogue migration (PR #358)

- [x] Keep OWNER diagnostics under DIAGNOSTICS_ACCESS_KEY plus HOMELAB_TRUSTED_CIDRS. Provide a 20-minute signed HttpOnly/Secure/SameSite=Strict owner-browser session; no credentials in persistent browser storage.
- [x] Remove the UI's raw v1 catalog HTTP request; the operational cards derive their state from the owner-only health board instead. On unauthorized access show the session unlock panel, never a fabricated probe failure.
- [x] Fix the deployment smoke contract: require unauthenticated catalog denial, not an unauthenticated private catalog dump.
- [x] Allow retirement of legacy /api/homelab-services and /api/public-homelab/v1 with HOMELAB_V1_HTTP_ENABLED=false; HTTP handlers return 410, never affect internal probes.
- [ ] Rollout: first migrate nabla-site-alban to Backstage v2, then set HOMELAB_V1_HTTP_ENABLED=false for FastAPI Cloud. The private /api/homelab-services OWNER route must remain protected even during the transition.
- [ ] Migrate remaining FastAPI *internal* legacy catalog/desired exposure inputs to Backstage v2 + authoritative topology before removing v1 JSON files. The flag changes only HTTP access, not background data sources.
- [ ] Validate trusted proxy peer addresses before setting HOMELAB_TRUSTED_PROXY_CIDRS. End-to-end HTTPS browser login, cookie expiry, owner CIDR, health boards, probe fan-out and full quality gate must be verified before deployment.

## P0 — public/private observability boundary (PR #353 / issue #352)
- [x] Site catalog service contract migrated directly to canonical Backstage v2: authenticated `GET /api/site/catalog/v2`, schemaVersion/model/catalogRevision/entities and dependency refs, strict field allowlist and 5-minute fresh-source TTL. No v1 site route, bootstrap or LKG. The source artifact is `nabla-compose/catalog/generated/entities.json` (pending PR #265 merge to master). See [consumer handoff](site-architecture-catalog-handoff.md).
- [ ] `nabla-site-alban`: consume the existing `parseHomelabCatalogV2()` / `catalogV2ServiceViews()` from the new `/api/site/catalog/v2`, remove v1/fallback, enforce Vercel server-only secret, source revision, private-owner gate and EN/FR Architecture. Coordinate with `nabla-compose` PR #265 and its generated v2 artifact; while unmerged, strict 503 (no v1 fallback). Frontend, Vercel and full local gate NOT_RUN.
- [ ] Audit every live HTTP/ASGI WebSocket mount, docs/OpenAPI, MCP, admin,
  health and HTML route on the exact deployed FastAPI SHA. Validate access
  policy classification, missing credentials and negative bypass tests.
- [ ] Verify signed Cloudflare Access JWT (RS256/JWKS, `iss`, `aud`,
  expiration and exact human identity); Service Token and owner policies
  remain distinct. Keep runtime strict mode disabled until all consumers
  use the public allowlisted DTO `/api/public-homelab/v1`.
- [ ] Coordinate removal of sensitive public static/site API projections in
  `nabla-site-alban`; only then deploy `ops.albandrieu.com` through
  private Traefik/Tunnel/Access in `nabla-compose`. Prove MFA, no origin
  bypass and rollback. Keycloak is not a P0 dependency.

## P0 — scanning and LAN-only DefectDojo
- [ ] Validate the weekly/manual `Docker CI` Trivy JSON artifact plus SARIF
  conversion from **one** scan. Check GH run SHA/event, exact ZIP, no secret
  evidence, size and expected product/engagement before enabling import.
- [ ] Keep PR Betterleaks and Trivy Critical/secret blocking; expand SCA,
  Semgrep, CodeQL, Nuclei and ZAP only at approved cost-aware cadence.
  Do not automatically publish sensitive DAST/PII/SBOM on GitHub.
- [ ] Test GitHub App `Actions:read` least privilege, LAN HTTPS/SNI to
  `defectdojo.int.albandrieu.com`, bot RBAC denied outside its engagement,
  Vaultwarden initialization and Celery import+dedup. No public DefectDojo.

## P1 — FastAPI staging → TrueNAS LiteLLM → workstation Qwen (2026-10-20)
- [x] Fail closed if LITELLM_URL is set without a virtual key; unit tests demonstrate `DEFAULT_CHAT_MODEL=fastapi-qwen` uses the TrueNAS gateway and does not route through Azure/OpenAI directly.
- [x] `nabla-compose` PR #263 declares the staging URL/model and routes `fastapi-qwen` → workstation `qwen`, with separate upstream/downstream key policy and an 8 USD nonresetting cap (more restrictive than 10 EUR target at usual exchange rates).
- [ ] Actually generate **both** scoped keys on trusted endpoints, store through Vaultwarden, verify both DBs and nonzero spend, test function calling/negative fallback, and deploy TrueNAS staging. These runtime operations are NOT_RUN.
- [ ] Cloud `fastapi-sample.fastapicloud.dev` is not connected: no authenticated transport to private LAN has been established. Do not set a private RFC1918 LiteLLM URL on cloud. Canonical [runbook in nabla-compose](https://github.com/AlbanAndrieu/nabla-compose/blob/docs/private-homelab-observability-boundary-20261018/docs/runbooks/fastapi-sample-litellm.md).

## P1 — Per-service Prometheus/Gatus and explicit fan-out coverage (2026-10-20)
- [x] Reuse the **existing** read-only `/api/health-board` fixed-query Prometheus snapshot for service-card badges; show Gatus observation, Prometheus scrape, and explicit job for PostgreSQL/pfSense/other mapped exporters. Show PostgreSQL `pg_up` separately from exporter `up`.
- [x] Explain eligible probe slots versus catalog services without targets, current-wave rotation, stale/unobserved evidence and LAN disabled; do not report missing evidence as a service outage.
- [ ] Deploy the corresponding `nabla-compose` Gatus labels for pfSense/PostgreSQL/TrueNAS and deduplicated Prometheus recording rules. Verify with `scripts/truenas/diagnose-prometheus-targets.sh` and `scripts/prometheus/audit-telemetry-coverage.py`; confirm exact service ID recording series and both exporter job states. Repository declarations are not runtime evidence.
- [ ] Validate service-card presentation behind Cloudflare Access after staging deploy and measure 3+ full rotating windows; retain external probes for outside-in context. A catalog with >12 eligible slots per scope cannot reach 100% on a single 30-second refresh.

- [ ] Convergence Gatus : vérifier depuis TrueNAS les séries réelles du job `gatus` et les règles Prometheus. Le `max by` actuel de `synthetic_probe_success` (propriétaire : `nabla-compose`) peut masquer un moniteur en échec si plusieurs ciblent le même service/protocole ; revoir avant toute délégation. Préserver en priorité les sondes WAN depuis FastAPI Cloud (DNS public/IP/ports déclarés, TLS, origine/Cloudflare Access), sans exporter les métriques privées. Audit approfondi et matrice de dépendances : [Gatus / Python](gatus-python-monitoring-convergence.md).

- [x] Guard outside-in HTTP against declared public names resolving to non-global A/AAAA addresses; no HTTP attempt and explicit unknown/warn, rather than performing a LAN request from cloud.
- [ ] Add peer-IP/DNS pinning to eliminate DNS rebind TOCTOU without compromising TLS SNI/Host, plus declared public TCP/port checks only after reviewing the approved targets; prove via tests without performing arbitrary scans.

## P1 — health, topology and runtime acceptance
- [ ] After an approved deployment, compare Garage external/internal probe
  phases over three cycles, unexpected admin Tunnel exposure and WAN NAT
  reflection. Separate `unknown` from an actually failed health check.
- [ ] Reconcile canonical `nabla-compose` topology IDs and Gatus telemetry
  from TrueNAS/Talos/Kubernetes/Prometheus; preserve cloud outside-in probes.
- [ ] `/healthz` : les enrichissements TLS LiteLLM/Pyroscope sont désormais
  concurrents (pire cas ≈ 5 s au lieu de ≈ 10 s) ; `build_homelab_health_payload`
  est découpé en helpers sans changement de contrat. Preuve restante : mesurer
  `refresh_elapsed_ms` et la latence `/healthz` avant/après sur un runtime
  déployé. Dette soldée : `route_policy_for` (équivalence vérifiée sur 3 136 cas
  chemin/méthode/type), `_register_homelab_catalog_routes`, le validateur
  PostHog `_validate`, `build_sickz_payload` (114 → 69 lignes), `probe_truenas`
  (126 → 46) et `_observe_posture_origin_bounded` (188 → 73 ; payloads de repli
  dans `pfsense_posture_skips.py`, JSON identique vérifié sur 401, preflight
  lent et nominal), `observe_pfsense_dns_posture` (155 → 56 ; 6 chemins),
  `check_pfsense_api` (119 → 66 ; 10 chemins) et
  `collect_truenas_network_diagnostics` (116 → 85 ; 4 chemins WAN), chaque
  fois JSON identique (clés + ordre) à l'implémentation précédente. Reste
  > 100 lignes : `render_api_root_page`, `render_topology_page` (HTML
  déclaratif, à externaliser en gabarit seulement si une évolution l'exige).
  Taille de fichiers : `sickz_policy.py` 655 → 416 (évaluation Cloudflare
  Tunnel/Access déplacée telle quelle dans `sickz_cloudflare_policy.py`, AST
  identique vérifié). Restent > 500 lignes : `external_probe_cache.py` (597),
  `pfsense_dns_observer.py` (547), `truenas_client.py` (536),
  `pfsense_security_observer.py` (535) — découper par responsabilité au
  prochain changement fonctionnel qui les touche.
- [ ] Contextes SSL partagés (`verified_ssl_context`/`unverified_ssl_context`) :
  chaque `httpx.AsyncClient(verify=True)` rechargeait le bundle CA (≈ 8 ms de
  CPU bloquant l'event loop, mesuré localement, contre 0,06 ms partagé) par
  cible sondée dans `/healthz`, `/sickz` et la sonde edge Cloudflare. Preuve
  restante : latence p95 `/sickz` et `/healthz` avant/après sur runtime déployé.
  Autres clients encore créés par requête (un seul par appel, gain marginal) :
  `platform_health`, `pfsense_*_observer`, `homelab_truenas_probe`.
- [ ] Verify changed runtime health and security posture with LAN evidence.
  Retain incident-specific symptoms, commands and recurrence criteria in
  [incidents.md](incidents.md) or the appropriate infrastructure runbook.

## P1 — local-first quality and reduced agent context
- [ ] Run focused pytest, workflow YAML validation and the repository's
  deterministic `scripts/agent-quality-gate.sh --fix` followed by clean
  `scripts/agent-publish.sh` on the exact HEAD. Report missing tools as
  **NOT_RUN**, never success. Do not spend CI credits just for formatting.
- [ ] Re-evaluate any item from the legacy backlog **before** restoring it
  to this roadmap. Retire completed/obsolete checklists rather than
  accumulating date-stamped status paragraphs.
- [ ] Evaluate Dagger only if it demonstrably improves measured local/CI
  parity without duplicate pipeline maintenance.
- [ ] **actionlint + zizmor** : exécutés en pre-commit et dans le job
  `preflight` de `python.yml` (`--all-files`, configuration
  `.github/zizmor.yml`, `.github/actionlint.yaml`). Résidus :
  - appels locaux passés à la syntaxe `$/` (audit zizmor `self-repository`
    actif) ; actionlint 1.7.12 ne la connaît pas : ses deux messages sont
    ignorés dans `.github/actionlint.yaml` (même correctif que
    wakam/Wakam#4131), ce qui le prive aussi de la vérification des
    `inputs`/`outputs` de ces workflows réutilisables. Preuve de clôture :
    actionlint accepte `$/…` → supprimer l'ignore ;
  - **NOT_RUN** : premier run GitHub d'un `uses: $/.github/workflows/…`
    (syntaxe récente) et de la nouvelle étape CI (local-first).
  - `mirrors-prettier` remplacé par `rbubley/mirrors-prettier` v3.9.10 ;
    reformatage cosmétique accepté, `secrets-enc.yaml` (SOPS) exclu.
- [x] `master-smoke.yml` conserve les contrôles en lecture seule et l'entrée
  manuelle/réutilisable ; son ancien déclenchement par `deploy.yml` est retiré
  car FastAPI Cloud déploie indépendamment.
- [ ] **Tests #353 corrigés** (23 échecs hérités) : client de test
  authentifié par clés factices (routes privées fail-closed), tests
  DefectDojo alignés sur l'API `private_file`/`validate_format`, contrats
  texte rendus robustes au reformatage ruff, fixture master-red sans
  historique manuel par défaut. Preuve : `agent-publish.sh` vert au HEAD.

## References and finish condition
- [Incident register](incidents.md): preserve unique diagnostic facts and
  recovery procedures that cannot be inferred from code.
- [Long-tail backlog](engineering-backlog.md): historical unchecked tasks
  requiring current verification.
- `AGENTS.md` / `.agents/skills/local-first-quality/SKILL.md`:
  source of truth for validation/evidence policy.
- No merge/deployment without instruction; status = PASS/FAIL/NOT_RUN
  linked to the exact commit and tested environment.

## Incident 2026-10-21 — Owner UI refusée en 403 depuis le domicile

L'IP IPv4 domestique confirmée par l'utilisateur est `82.66.4.247`. Une sortie
`curl -4` ne prouve pas que le navigateur utilise IPv4 (IPv6 peut être
préférée), ni que FastAPI Cloud voit cette IP derrière son ingress/proxy.

La connexion sur `POST /api/ui/session` distingue désormais dans sa réponse
**sans adresse source ni secret** :
- `503 code=unconfigured` : la variable `DIAGNOSTICS_ACCESS_KEY` manque au runtime.
- `403 code=origin_unverified` : l'origine HTTPS/Host/Sec-Fetch-Site ne concordent pas.
- `403 code=source_unverified` : le serveur ne peut pas vérifier une IP
  cliente appartenant à `HOMELAB_TRUSTED_CIDRS`.
- `401` : une clé incorrecte, **seulement** si l'origine et le réseau sont autorisés.

Préserver l'ordre origin → réseau → comparaison du secret : il empêche qu'un
attaquant externe utilise l'endpoint comme oracle de vérification de clés.
Éviter d'enregistrer/afficher les valeurs de headers ou la clé.

**Actions runtime non réalisées** :
1. Inspecter via `mise exec -- uv run fastapi cloud env list` la **présence**
  de `DIAGNOSTICS_ACCESS_KEY`, `HOMELAB_TRUSTED_CIDRS` et
  `HOMELAB_TRUSTED_PROXY_CIDRS`, sans afficher de secrets.
2. Vérifier l'origine de la requête, l'IP de peer ASGI et la provenance
  réellement vérifiée de `X-Forwarded-For` **dans les logs privés**, sans
  diffuser les valeurs. Une chaîne multi-proxy peut être légitime, mais il
  faut prouver les pairs de confiance avant d'élargir son interprétation.
3. N'approuver dans `HOMELAB_TRUSTED_PROXY_CIDRS` que les adresses de
  proxy ingress contrôlées et vérifiées ; jamais `0.0.0.0/0`, `::/0`,
  l'ensemble des IP cloud, ni une variable `FORWARDED_ALLOW_IPS=*`.
4. Déployer et tester depuis IPv4/IPv6, réseau tiers, en-tête forgé, et cookie
  expiré. Réponse `403` sans données opérationnelles en cas de provenance
  invérifiable. Les sondes cloud restent indépendantes de cette session.

## P0 — FastAPI Cloud owner access blocked (2026-10-21)
- [x] Diagnose failed production deploy jobs 39634265656 / 39562478704; the original 403 UI predates GitHub master and may indicate an older cloud runtime.
- [x] Restore deterministic tests for draft CI scope, monotonic stale caches, INTERNAL metrics authentication and v2 catalog route mocking; clarify the 403 browser message without exposing secrets or changing the CIDR policy.
- [ ] Validate the Python quality gate on exact PR HEAD and merge only after approval; deploy and verify the production runtime SHA.
- [ ] Diagnose FastAPI Cloud ingress peer and proven header rewriting privately before configuring HOMELAB_TRUSTED_PROXY_CIDRS. Test 200 home, 403 outside, 401 wrong key, and 403 spoof attempts.

## P0 — Temporary minimal public service display on /api (2026-10-21)
- [x] Operator-approved temporary service directory in /api while the Cloud owner CIDR/proxy is broken: GET /api/ui/services returns **only** validated Backstage v2 labels, kind, and enum health states (OK/WARN/FAIL/UNKNOWN), never raw diagnostics or service endpoints. Existing OWNER diagnostics remain protected.
- [x] Opt-out: HOMELAB_UI_PUBLIC_SERVICES_ENABLED=false returns 404 and hides the temporary feed, default true until owner admission is repaired and verified. This intentionally makes a minimal inventory PUBLIC while enabled; retire immediately after the real owner session is restored.
- [ ] Validate live service states/coverage (entityRef mapping still incomplete), Swagger/OpenAPI inventory exposure, click-through filters, mobile view and security negative tests. No public raw IPs, internal URLs, ports, credentials, probe evidence or dependency graph.
- [x] Le workflow GitHub de déploiement redondant est retiré ; FastAPI Cloud déploie indépendamment. Ne jamais déduire un runtime actif d'une release GitHub.

- [x] Frontend safety net: on stale/pending status DTO or failed refresh, reset all observed statuses to UNKNOWN while preserving a previously loaded service roster in volatile memory (no localStorage). Offline DOM smoke confirms 42 labels survive a 503, never retaining stale OK.

## P0 — FastAPI Cloud deployment token-only CLI (2026-10-22)
- [x] Evidence: Actions 39819073386 validation PASS but deploy fails with `No credentials found` on the first `fastapi cloud env set`, before `fastapi deploy`. Token and app ID were non-empty.
- [x] Separate trusted-operator environment management from deploy-only automation, remove five in-pipeline `cloud env set` mutations. Stamp Git SHA into an uploaded tracked module; `/v2/version.build_revision` still attests the exact checkout.
- [ ] Before deployment, verify cloud variables `DEBUG=false`, posture/security TLS verify=true and authenticated pfSense probes=true from a trusted operator; no automatic change is implied by the deploy-token job.
- [ ] Validate full local quality gate; merge/deploy only on approval; verify exact deployed revision and the temporary `/api/ui/services` feed.
- [x] FastAPI Cloud gère déjà le déploiement direct ; aucune pipeline GitHub de déploiement n'est nécessaire.

## P0 — Suppression de la pipeline redondante (2026-10-22)

- [x] Retirer `.github/workflows/deploy.yml` et tous ses jobs de validation, déploiement CLI et smoke couplé : aucun `fastapi deploy` ni `fastapi cloud env set` ne doit exister dans `.github/workflows`.
- [x] Garder l'événement `semantic-release-published` exclusivement pour `release.yml` (packages, pas déploiement application). `master-smoke.yml` reste autonome et manuel/réutilisable ; ne pas déclencher de vérification distante payante.
- [x] Remplacer les tests couplés à `deploy.yml` par des tests de propriété négatifs (non-déploiement, absence de token Cloud dans les workflows GitHub, déclencheur package préservé).
- [ ] Valider tous les tests pertinents sur un checkout complet avant fusion. Aucun déploiement automatique et aucune CI GitHub ne doivent être sollicités pour cette PR. L'état de production FastAPI Cloud doit être vérifié séparément en lecture seule.
