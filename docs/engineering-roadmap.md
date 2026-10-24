# Engineering roadmap — fastapi-sample

**Réconciliation inter-dépôts : 24 octobre 2026.** Ce document contient uniquement les livrables **FastAPI** et leurs tests d'acceptation. Les migrations et décisions de déploiement TrueNAS/pfSense/Talos sont dans la [roadmap Compose](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap.md). Le rendu ReactFlow/cartes et Vercel sont dans la [roadmap Site Alban](https://github.com/AlbanAndrieu/nabla-site-alban/blob/master/docs/homelab-roadmap.md). Détail des anciennes 84 tâches ouvertes dans [l'historique du fichier avant réconciliation](https://github.com/AlbanAndrieu/fastapi-sample/blob/38c03139a6ebf7986b31dab1915566dac8935c03/docs/engineering-roadmap.md), qui n'est pas un deuxième backlog actif.

**Statut :** [PR #373](https://github.com/AlbanAndrieu/fastapi-sample/pull/373) fusionnée le 24/10 à 16:28 UTC ; ce merge ne prouve pas la révision déployée sur FastAPI Cloud/TrueNAS. Conserver `NOT_RUN` quand aucune sortie de test n'existe.

## P0 — Comparaison DNS workstation/TrueNAS (24 octobre 2026)

**Observation de la workstation fournie le 24/10 à 19:34 CEST, non extrapolable à TrueNAS :**
- PfSense/Unbound `172.17.0.1` renvoie `sample.int.albandrieu.com A 172.17.0.24` en **25 ms** (TTL 0).
- Le même résolveur renvoie des adresses IPv4 **publiques Cloudflare** pour `sample.albandrieu.com` en **20 ms** ; leur valeur n'est pas un invariant.
- Après `nmcli`, `eno1` utilise `172.17.0.1`, et `getent ahostsv4 sample.int.albandrieu.com` renvoie `172.17.0.24`. Première requête `resolvectl` interne : **6,0703 s**, contre **53,9 ms** pour le nom public ; cette durée ne permet pas d'attribuer la cause à Unbound ou DNS-over-TLS.
- **TrueNAS : NOT_RUN** depuis cet environnement. Le DNS d'un hôte ne prouve pas le DNS de ses conteneurs Docker.

- [x] Ajouter `scripts/diagnose-homelab-dns.py` (bibliothèque standard, read-only) : comparer les réponses directes pfSense `dig` aux réponses système `getent` pour les deux noms, avec timeout et statut explicite `matched/unverified/*_mismatch`.
- [x] Ajouter `--dns-only --vantage workstation|truenas` à `scripts/truenas-runtime-evidence.sh` ; recettes `just dns-evidence-workstation` et `just dns-evidence-truenas`. Le mode strict refuse les preuves absentes ; aucun accès API, Docker ou Cloudflare n'est implicite.
- [ ] Exécuter sur la workstation, puis sur TrueNAS, les deux recettes depuis le checkout FastAPI ; archiver uniquement date, observateur, latences et résultats expurgés. Contrôler ensuite séparément `just truenas-evidence` et les sondes HTTP/TCP/TLS/API, sans considérer une simple réponse DNS comme un succès applicatif.
- [ ] Exécuter sur le HEAD complet les tests `tests/unit/test_diagnose_homelab_dns.py`, `test_truenas_runtime_evidence_wrapper.py`, Ruff et `just quality` ; les tests du helper ont passé **5/5 en copie locale isolée**, pas encore la suite sur checkout complet.

**Done :** workstation et TrueNAS observées indépendamment ; le cache DNS, le trafic IPv6 et les accès Cloudflare ne sont pas confondus avec la santé de l'origine FastAPI.

## P0 — Contrat de sondes HTTP/TCP/TLS et fraîcheur par service

- [ ] Valider localement l'implémentation `internal_probe_execution` (schéma OWNER v6) : `disabled`, `not-configured`, `not-executed`, `stale`, `failed`, `observed`. La valeur `RUNNING` de Docker n'est pas un succès TCP.
- [ ] Produire une preuve OWNER par `entityRef` et voie de mesure (HTTP/HTTPS, TCP, TLS, DNS, Cloudflare, runtime) avec source, statut, observé à, âge, éventuel timeout et raison bornée. Ne pas substituer le `checked_at` global aux horodatages de sondes.
- [ ] Comparer une réponse du collecteur TrueNAS **interne** à FastAPI Cloud : Cloud ne doit pas activer `HOMELAB_INTERNAL_PROBES_ENABLED` ni accéder au LAN. Conserver `internal_probes_enabled=false` en cloud si c'est sa configuration effective ; afficher `disabled` et non `fail`.
- [ ] Vérifier la rotation bornée : 12 sondes publiques par cycle, éligibilité vs couverture récente, sources `origin/memory/deadline`, limites concurrence/timeout et rétention des mesures anciennes. Ne pas provoquer de fan-out additionnel vers pfSense.
- [ ] Vérifier les cas HTTP 302/403 Cloudflare Access : atteinte de la passerelle ≠ origine saine ; sondes publiques et sondes authentifiées internes restent indépendantes.

**Done :** trois cycles cohérents avec preuves datées par service, tests pytest/ruff locaux et DTO OWNER explicite, sans état fabriqué.

## P0 — Reconciler TrueNAS, Cloudflare, Gatus et Prometheus

- [ ] Conserver l'identité canonique `entityRef` issue du catalogue Compose ; refuser les jointures ambiguës par nom lorsque plusieurs ressources partagent un libellé.
- [ ] Contrôler la santé de l'application TrueNAS **et** du conteneur principal, notamment `prometheus` App RUNNING / conteneur `exited`. Les conteneurs d'initialisation terminés ne doivent pas donner un faux rouge. Marquer `runtime_primary_container_issue` seulement sur une observation récente et non ambiguë.
- [ ] Ajouter un signal métier borné par `entityRef` pour Gatus, Prometheus et exporters : dernier scrape, âge, `up`, `pg_up`, probe réseau spécifique et raison `not-configured/not-observed/failed`. Un exporter `RUNNING` n'atteste pas des métriques valides.
- [ ] Publier un indicateur explicite de dérive entre cibles déclarées et observées, sans corriger les routes : Gatus, Bichon, Garage Web UI/Admin. Le catalogue et les routes effectives restent propriété de Compose.
- [ ] Distinguer `local_state`, `dependency_state`, `effective_state`, `blocked_by`, `degraded_by` et observations non confirmées, sans nouvelle logique parallèle dans le navigateur.

**Done :** toutes les mesures produites par l'API sont traçables à leur collecteur et la santé conflictuelle ne devient jamais silencieusement `ok`.

## P0 — Frontière OWNER/SERVICE et UI FastAPI Cloud

- [ ] Maintenir les read-models SERVICE v2 expurgés (`catalogRevision`, `entityRef`, états publics publiables). Refuser toute fuite d'IP privée, clés, réponses de sondes, payloads de posture ou routage interne vers des consommateurs anonymes.
- [ ] Conserver la protection OWNER et les sessions signées, HttpOnly, temporaires. Vérifier séparément accès LAN, service token Cloudflare Access, réponse 401/403 et refus de l'origine ; ne pas interpréter un 403 public comme un service indisponible.
- [ ] Vérifier sur FastAPI Cloud `/api`, `/api/health-board`, `/api/homelab/health`, `/api/homelab/probes`, `/api/site/catalog/v2`, avec scénarios anonymes/propriétaire ; une UI minimale ou refusée peut être une régression de l'autorisation.
- [ ] Harmoniser les cartes, filtres et explications de protocoles **dans l'UI native FastAPI** ; ne pas réécrire les composants React du site ou son routage Vercel.
- [ ] Revalider la configuration publique temporaire de diagnostics read-only puis planifier son retrait avec une solution OWNER MFA/LAN éprouvée, sans couper brutalement le catalogue SERVICE.

**Done :** modèles SERVICE et OWNER vérifiés indépendamment, sorties refusées sûres, tests des permissions et de l'UI native au SHA réellement déployé.

## P0 — Qualité, versions et déploiement FastAPI

- [ ] Exécuter `pytest tests/unit/test_homelab_service_health.py`, le pack API/health et `just offline-l1`, `just p0`, `just quality` sur le HEAD exact, avec Ruff/typecheck/tests de secrets. Corriger les échecs avant release.
- [ ] Confirmer la compatibilité et les mises à niveau Python, FastAPI, Pydantic et dépendances avec **le runtime réellement disponible** sur FastAPI Cloud et TrueNAS ; ne pas déduire une version installée d'un document upstream.
- [ ] Vérifier que le déploiement FastAPI Cloud est géré par sa plateforme native et ne recréer aucune pipeline GitHub de publication non nécessaire. Utiliser [skip ci] pour les commits documentaires et ne pas dépenser les quotas Actions.
- [ ] Garder un tracker unique des échecs master CI qui respecte les modifications manuelles des issues et ferme après deux succès consécutifs ; ne pas générer une issue par run.
- [ ] Réconcilier les contrats local-first avec Site Alban et Bababou seulement pour les outils communs, sans intégrer leurs contenus ni séparer le code propriétaire.

## P1 — Télémetrie, modèles, sécurité et intégrations

- [ ] Récupérer les métriques de Prometheus/Gatus via les collecteurs autorisés (requêtes fixes, cardinalité bornée) et proposer au site un DTO versionné ; ne pas publier les credentials d'exporters.
- [ ] En staging **TrueNAS**, vérifier le chaînage FastAPI → LiteLLM TrueNAS → LiteLLM workstation, avec clé dédiée à budget et secrets dans Vaultwarden ; la création du secret et le réseau appartiennent à Compose.
- [ ] Stabiliser l'intégration Sentry/OTEL/Pyroscope, la disponibilité des backends et la dégradation contrôlée sans impacter liveness/readiness.
- [ ] Préparer uniquement l'export contrôlé des événements métier PostHog déjà autorisés, désactivé par défaut ; ne pas intégrer de trackers dans des API OWNER.
- [ ] Livrer les rapports expurgés Trivy/Semgrep/ZAP/Nuclei que collecte DefectDojo côté Compose ; conserver formats, provenance SHA/run et confidentialité, sans importer depuis FastAPI Cloud.
- [ ] Garder SAST/DAST/SCA, règles secrets, dépendances et contrôle des ressources en complément des preuves de runtime.

## Dépendances — ne pas implémenter ici

| Dépôt propriétaire | Travail et limite |
| --- | --- |
| [Compose](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap.md) | TrueNAS Apps, Prometheus déploiement, port Gatus/Garage, Cloudflare Tunnel, pfSense/DNS, pflow/Akvorado, Talos/K8s, OpenRAG/Docling, Vaultwarden, collecteur LAN et automatisations DefectDojo |
| [Site Alban](https://github.com/AlbanAndrieu/nabla-site-alban/blob/master/docs/homelab-roadmap.md) | Build Next.js/Vercel, icônes et cartes, ReactFlow, traduction FR/EN, cache SERVICE navigateur, UX et accès OWNER aux pages |

**Règle de clôture :** une PR fusionnée n'est pas un déploiement. Contrôler les contrats, les horodatages des sondes et la protection des données sur le runtime cible. Les incidents datés et historiques de migrations restent dans `docs/incidents.md` et l'historique Git.
