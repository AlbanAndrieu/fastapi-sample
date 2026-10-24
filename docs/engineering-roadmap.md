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
