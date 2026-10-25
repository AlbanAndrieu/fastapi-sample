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
- [ ] Exécuter les deux suites sur un checkout complet au SHA de la PR et corriger les régressions observées. Le runner agent possède Node 22.16.0/npm 10.9.2, mais le checkout Git n'est pas accessible depuis cet environnement (DNS GitHub indisponible). **NOT_RUN**, jamais PASS implicite.
- [ ] Conserver le contrôle complet séparé avec Node >=24.22.1, requis par `package.json`; ne pas abaisser cette contrainte pour permettre un test isolé.

### UX et convergence Gatus — critères d'acceptation

- [ ] Dans chaque drawer, regrouper les éléments par DNS, TCP, TLS, HTTP, Cloudflare Access/token, Prometheus/exporter et Gatus ; afficher verdict, code d'erreur expurgé, timestamp, âge, provenance et remédiation.
- [ ] Ajouter URL partageable `?service=<id>`, filtre `failed evidence only`, focus clavier, historique de navigation entre dépendances et affichage mobile compact.
- [ ] Afficher les relations amont/aval avec lien uniquement si l'ID canonique existe dans le snapshot autorisé ; signaler les dépendances absentes sans URL réseau privée.
- [ ] Réconcilier la couverture Gatus : déclarées / observées / sans échantillon / absentes / volontairement désactivées, par ID canonique et point d'observation. Ne jamais déduire que toutes les sondes sont vertes de `up{job="gatus"} == 1`.
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
- [ ] Après diagnostic Gatus LAN (owner Compose), rapprocher
  son nombre de sondes déclarées, les dernières mesures et les
  `nabla_service_id` observés ; isoler les sondes volontairement
  arrêtées des véritables pannes, sans falsifier les critères.
- [ ] Proposer un filtre `failed evidence only`, une URL partageable
  `?service=<id>`, navigation retour entre services, et historique
  de latence/availability 5m uniquement si les mesures sont fraîches.

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
