# Gatus, AutoKuma et services Python — audit de convergence

**Analyse de source : 20 octobre 2026.** Repos amont consultés sur leur branche par défaut. Les versions citées décrivent les manifestes consultés, pas nécessairement les images déployées sur TrueNAS. Aucun service, accès réseau ou schéma de données n'est modifié par ce document.

## Conclusion

**Conserver Gatus comme sondeur interne**, Prometheus comme interface de télémétrie et `fastapi-sample` comme agrégateur Python en lecture seule. **Conserver les sondes cloud outside-in** indépendantes : une réussite depuis TrueNAS ne prouve pas l'exposition publique ; une erreur côté WAN ne prouve pas une panne du conteneur. Ne pas introduire un deuxième moteur de supervision sans preuve de valeur et de coût.

| Projet | Langage / rôle | Dépendances structurantes | Avis |
| --- | --- | --- | --- |
| [Gatus](https://github.com/TwiN/gatus) | Go, sondeur HTTP/TCP/DNS/ICMP et dashboard | `gofiber/fiber/v2`, `miekg/dns`, `prometheus/client_golang`, `pro-bing`, `modernc.org/sqlite`, `lib/pq`; stockage mémoire/SQLite/PostgreSQL | **Conserver** ; utiliser `/metrics` en réseau privé |
| [AutoKuma](https://github.com/BigBoot/AutoKuma) | Rust, provisionnement de moniteurs **Uptime Kuma**, pas un sondeur autonome | `bollard` (Docker), `kube` option Kubernetes (fonctionnalité par défaut), `rust_socketio`, `tokio`, `reqwest`, `sled` | Ne pas substituer à Gatus ; source supplémentaire de dépendances et d'identifiants |
| [Uptime Kuma](https://github.com/louislam/uptime-kuma) | JavaScript/Node.js, supervision et status page | Serveur Node.js et stockage du moniteur | Réutiliser si besoin UI/alerting, éviter le double polling systématique |
| [Healthchecks](https://github.com/healthchecks/healthchecks) | **Python/Django**, heartbeats de crons / tâches | `Django==6.1.2`, `psycopg==3.3.6`, `cronsim==2.7`, `pydantic==2.14.1`, `pycurl` | Complément pour tâches asynchrones, **pas** remplacement des sondes HTTP/TCP/DNS |
| [Cabot](https://github.com/arachnys/cabot) | Python/Django, vérifications de disponibilité | Manifeste inspecté : `Django==1.11.29`, `celery==4.2.1`, Redis, PostgreSQL | **Écarter** : pile manifestement obsolète, risque de sécurité/maintenance |
| [Tech Sentinel Monitor](https://github.com/ronaldgoodchild/tech-sentinel-monitor) | **Python/FastAPI**, probes HTTP/TCP/ping/heartbeat et status page | `asyncpg`, `redis`, `httpx`, `pydantic-settings` ; **TimescaleDB**, Redis Streams, workers et service status-page distinct | Alternative fonctionnelle à évaluer, mais infrastructure redondante et maintenance/sécurité à auditer |
| [Watchpost](https://github.com/RyukXO-code/watchpost) | **Python/FastAPI** + React, monitoring HTTP et UI | `httpx==0.28.1`, `anyio==4.12.1`, `APScheduler==3.11.2`, `fastapi-mail`, frontend Node/Vite | Bibliothèques proches de FastAPI ; historique persistant et authentification annoncés comme roadmap, donc pas équivalent production |
| [API Status Monitor](https://github.com/mkami28/API-Status-Monitor) | **Python/FastAPI**, HTTP / dernier statut en mémoire | FastAPI, configuration YAML, Docker ; projet déclaré alpha et pas de persistance | POC simple, mais régression fonctionnelle face à Gatus ; ne pas substituer en production |

Sources vérifiables : [Gatus go.mod](https://github.com/TwiN/gatus/blob/master/go.mod), [Gatus metrics](https://github.com/TwiN/gatus/blob/master/metrics/metrics.go), [Gatus README](https://github.com/TwiN/gatus/blob/master/README.md), [AutoKuma Cargo.toml](https://github.com/BigBoot/AutoKuma/blob/master/Cargo.toml), [AutoKuma client](https://github.com/BigBoot/AutoKuma/blob/master/kuma-client/Cargo.toml), [Healthchecks requirements](https://github.com/healthchecks/healthchecks/blob/master/requirements.txt), [Cabot requirements](https://github.com/arachnys/cabot/blob/master/requirements.txt), [Tech Sentinel control-plane](https://github.com/ronaldgoodchild/tech-sentinel-monitor/blob/main/control-plane/requirements.txt), [Tech Sentinel probe-worker](https://github.com/ronaldgoodchild/tech-sentinel-monitor/blob/main/probe-worker/requirements.txt), [Tech Sentinel Compose](https://github.com/ronaldgoodchild/tech-sentinel-monitor/blob/main/docker-compose.yml), [Watchpost requirements](https://github.com/RyukXO-code/watchpost/blob/main/requirements.txt). Comparer les versions installées séparément.

## Code existant et dépendances à mutualiser

- `nabla/api/homelab_probe_runner.py` : HTTP via `httpx.AsyncClient`, TCP via `anyio.connect_tcp` et contrôles DNS via `nabla/api/dns_probe.py` (`dnspython`). Conserver uniquement les cas spécifiques et l'observation outside-in lorsqu'ils ne sont pas déjà couverts depuis le même point de vue.
- `nabla/api/prometheus_query.py` : requêtes PromQL instantanées fixes et validation stricte des résultats. **Réutiliser ce client** plutôt qu'ajouter un SDK Gatus tiers, un proxy ou un scraping public.
- `nabla/api/synthetic_probe_comparison.py` : observations `gatus_via_prometheus`, comparaison des seuls transports compatibles et décision `shadow_only`. Les preuves `HTTP`/ `HTTPS` restent des observations applicatives distinctes des preuves `TCP`.
- `nabla/api/homelab_dependency_health.py` : propagation des défaillances de dépendances de topologie, à garder distincte d'une absence de métriques.
- `nabla/api/data/homelab-services.json` : catalogue projet ; aligner les IDs avec la source d'autorité `nabla-compose`, pas avec des labels arbitraires de Prometheus. Ne pas publier les chemins internes, adresses, jetons ou alertes privées.

**Ne pas ajouter de dépendance Python de supervision dans `pyproject.toml` pour ce seul objectif** : `httpx`, `anyio`, `dnspython`, `prometheus-client` et Pydantic y sont déjà présents. Ajouter Healthchecks signifierait déployer et maintenir une seconde application Django/DB pour un cas d'usage différent.

**Pourquoi ne pas migrer tout de suite vers une alternative FastAPI ?** Tech Sentinel reproduit plusieurs fonctions de Gatus mais ajoute TimescaleDB, Redis, workers et un front ; il faut examiner les tests, l'activité de maintenance, l'authentification, le modèle RBAC, la gestion des migrations et les correctifs de sécurité avant un POC isolé. Watchpost partage `httpx`/`anyio` avec notre code et apporte APScheduler, mais son README prévoit encore persistance et authentification. API Status Monitor est un exemple pédagogique avec statut en mémoire. La convergence la moins coûteuse reste donc d'exploiter nos bibliothèques Python existantes, **sans recopier le scheduler ou l'UI de Gatus**.


## Audit approfondi des dépendances Python et du code source

See [the Site Alban pre-Keycloak API handoff](site-architecture-catalog-handoff.md). The site must consume a filtered service-only DTO, not the rich CIDR-protected catalog, and must not serve its local fallback on upstream failures.


### Ce qui est directement réutilisable

| Mécanisme étudié | Projet amont | Constat dans le code | Convergence proposée |
| --- | --- | --- | --- |
| Répartition des sondes avec quota | Tech Sentinel `probe-worker/worker/main.py` | Redis Streams (`XREADGROUP`, `XACK`), sémaphore `asyncio` ; `_reschedule_job` est lancé par `create_task` puis dort en mémoire | Notre fan-out borné et notre cache monotone existent déjà. Garder la concurrence limitée ; étudier un scheduler durable seulement si on ajoute du polling persistant |
| HTTP, TCP et ping | Tech Sentinel `worker/probes/*` | `httpx.AsyncClient` par sonde, `follow_redirects=True`; `asyncio.open_connection` pour TCP ; subprocess `ping` | Réutiliser `httpx`, `anyio.connect_tcp` et `dnspython` actuels ; conserver `follow_redirects=False` pour empêcher la redirection d'un contrôle WAN vers un hôte tiers / privé |
| Alerte de transition UP/DOWN | Watchpost `app/monitor.py` | Détection des changements d'état et notification asynchrone, historiques en mémoire | Intéressant pour un éventuel moteur d'incidents, mais ajouter seuils/flap damping, reprise et idempotence avant alerte ; ne pas confondre statut HTTP 403 Access et origine indisponible |
| Scheduler | Watchpost `app/main.py` | `AsyncIOScheduler` démarré au lifespan, pas de coordination multi-réplicas apparente | **Ne pas ajouter APScheduler** à FastAPI Cloud en production multi-workers : polling en double / écarts lors d'un redéploiement. Garder cache et cadence déterministe existants |
| Observation par lots | API Status Monitor `app/monitor.py` | `asyncio.gather` sur tous les endpoints, `follow_redirects=True`, nouveaux `httpx.AsyncClient` par endpoint | Ne pas reprendre tel quel : risque de rafale réseau, absence de contrôle de provenance et de persistance. Notre budget 12 slots/30s + sémaphore 4 est plus sûr |
| Surveillance de jobs | Healthchecks `hc` et `requirements.txt` | Django, `cronsim` pour expressions cron, `psycopg` pour stockage, `pycurl` | `cronsim` est le seul candidat intéressant si validation de retards cron nécessaire ; ne pas installer la stack Django complète |
| Contrats modèles / auth | Tech Sentinel `control-plane` | `pydantic-settings`, `asyncpg`, `redis`, `python-jose`, `passlib` | Déjà `asyncpg`, `redis`, Pydantic/Settings et authentification dans le repo ; ne pas importer `python-jose` ni `passlib` sans justification et audit sécurité |

**Dépendances candidates** : `cronsim` = seulement pour les tâches cron/heartbeat ; `APScheduler` = non retenu tant que le scheduler central de Gatus est présent ; `asyncpg` et `redis` = déjà installés ; `httpx`, `anyio`, `dnspython`, `tenacity`, `prometheus-client` = déjà installés, privilégier une adaptation typée et testée plutôt qu'une nouvelle dépendance. **Aucun ajout au lockfile demandé.**

**Anti-patterns observés** : `follow_redirects=True` dans les exemples amont peut masquer une redirection vers une origine différente ; une boucle `asyncio.gather` sans limite peut générer une rafale ; les tâches de réplanification créées en mémoire par `asyncio.create_task` dans Tech Sentinel ne sont pas une garantie de persistance après crash ; les schedulers par processus requièrent un leader/lease en multi-workers. Ces limites sont des constats de code, pas une évaluation globale de qualité des mainteneurs.

## Audit télémétrie déclaré vs observé — frontière réseau

**Topologie vérifiée statiquement dans [nabla-compose](https://github.com/AlbanAndrieu/nabla-compose)** : `apps/gatus/compose.yml` utilise Gatus `v5.36.0`, écoute dans le conteneur sur `:8080` et publie `:8085` sur TrueNAS ; `apps/gatus/config/config.yml` indique `metrics: true` et stockage SQLite. `apps/prometheus/prometheus.yml` déclare le job `gatus` et un scrape de 30 s vers `172.17.0.24:8085/metrics`. `apps/prometheus/rules/nabla-service.rules.yml` déclare :

- `nabla:telemetry:gatus_up` = état du **scrape**, pas des services ;
- `nabla:service:synthetic_probe_success` = jauge `gatus_results_endpoint_success` labellisée (`nabla_service_id`, `type`) ;
- `nabla:service:synthetic_probe_duration_seconds` = durée ;
- `nabla:service:synthetic_availability_ratio_5m` = ratio calculé sur compteurs `gatus_results_total`.

**Point critique à corriger dans nabla-compose** : la règle `synthetic_probe_success` utilise `max by (...)`, ce qui peut **masquer un échec** si deux moniteurs partagent `nabla_service_id` et `type` et qu'un seul réussit. Évaluer `min by (...)` avec un test multi-moniteurs, ou mieux une identité de moniteur stable, avant de déléguer. Modifier la règle dans son dépôt propriétaire (pas dans `fastapi-sample`). Le label existe déclarativement pour PostgreSQL, pfSense, TrueNAS ; le déploiement effectif est **non prouvé**.

The outside-in HTTP runner now denies an initial DNS resolution to any non-global IP (including RFC1918/link-local/ULA) before issuing HEAD/GET, reports a distinct warning, and preserves phase counters. This protects the cloud observer from accidental DNS misconfiguration, but a DNS time-of-check/time-of-use rebind remains a residual risk until the HTTP transport pins vetted resolved addresses. Do not confuse this with proof that an origin port is closed.

**Observation extérieure tentée** : depuis l'outil HTTP externe, `https://gatus.albandrieu.com/`, `https://prometheus.albandrieu.com/` et `https://sample.albandrieu.com/api` ont retourné **403**. Cela prouve seulement que ces URLs n'ont pas livré leurs données anonymement depuis cet observateur. Cela **ne prouve pas** la santé de Gatus, une règle de firewall particulière, l'absence de bypass direct IP:port ou le succès de Cloudflare Access. `https://fastapi-sample.fastapicloud.dev/api?q=Gatus` n'était pas accessible via l'outil ; aucun état runtime ne peut en être inféré. Aucun accès aux IP RFC1918 ou secret, aucune requête prometheus privée depuis Internet.

### Recette read-only à exécuter sur TrueNAS (et non dans FastAPI Cloud)

```bash
cd /mnt/cpool/compose/nabla-compose
python3 scripts/prometheus/audit-telemetry-coverage.py \\
  --prometheus-url http://127.0.0.1:9090
python3 scripts/truenas/reconcile-gatus-catalog.py \\
  --output /tmp/gatus-catalog-declared.json
# Lire uniquement les agrégats redigés par ces scripts ; ne pas committer les sorties.
```

Examiner ensuite (depuis le LAN uniquement) `up{job="gatus"}`, `gatus_results_total{job="gatus"}`, la présence des quatre règles et le nombre d'IDs canoniques observés, le statut/récence des samples, les conflits de métriques doublonnées et les services absents. Comparer l'exporter PostgreSQL `up` à `pg_up`. Les échecs de scrape doivent apparaître comme `unobserved/unknown` et non `service DOWN`. Les scripts existants de `nabla-compose` constituent la première preuve, pas des valeurs inventées.

### Contrat prioritaire : vantage FastAPI Cloud **depuis Internet**

`fastapi-sample.fastapicloud.dev` est extérieur au LAN et doit rester une sonde indépendante des métriques Gatus internes. Les sources d'autorité sont 1) le catalogue d'exposition déclaré, 2) Cloudflare Tunnel/Access et 3) le comportement **réel** DNS/TLS/HTTP depuis la sortie réseau du service cloud. Le LAN fournit seulement du contexte secondaire. À respecter :

1. **DNS public** A/AAAA + IP observées, CNAME/proxy Cloudflare vs IP homelab, cohérence avec l'inventaire d'exposition ; ne jamais exposer en API publique la topologie interne ou des tokens. `dnspython` sert déjà à ce préflight.
2. **Ports** : vérifier les seuls ports/IP explicitement autorisés du périmètre WAN déclaré (par exemple l'accès pfSense/TrueNAS prévu), en TCP et TLS dans un budget strict, avec critères de refus si redirection, DNS changé ou IP non autorisée. Pas de scan de plage/IP arbitraire ni de découverte LAN depuis le cloud ; le **403 Cloudflare** est une preuve de bordure HTTP, non de fermeture du port origine.
3. **Sécurité** : certificat et SNI, expiration, en-têtes de sécurité, Cloudflare Access (JWT machine/humain séparés), origin bypass, NAT/reflection, services indûment exposés. Une erreur CORS ne remplace pas un contrôle d'accès. Le cas échéant, différencier CONNECT/TLS/HTTP, et `FAIL`, `WARN`, `UNKNOWN` selon la phase.
4. **Provenance** : aucune variable proxy `HTTPS_PROXY/ALL_PROXY` ne doit faire prendre une observation depuis le proxy comme une mesure de la sortie FastAPI Cloud. D'où `trust_env=False` ajouté aux sondes HTTPS publiques et à l'echo IP (sous réserve du fonctionnement effectif des sorties cloud ; échec = preuve indisponible).
5. **Isolation** : `HOMELAB_PROMETHEUS_URL` ne doit pas être renseigné sur le déploiement cloud tant qu'aucun transport privé authentifié et justifié n'est approuvé. Ne jamais exposer Prometheus, Gatus `/metrics` ou une API interne pour améliorer la couverture des badges.

La priorité d'acceptation est **WAN outside-in > preuve Access/origine > métriques Gatus shadow-only**, avec deux perspectives séparées. Toute intégration future ajoute `observed_at`, `vantage_point`, `probe_protocol`, `target_identity`, `evidence_state`, `freshness` avant une décision de sécurité ; un scrape `up=1` n'est jamais une attestation de non-exposition.

## Gatus : contrat technique utile, limites et sécurité

Gatus expose les résultats d'endpoint via `/api/v1/endpoints/statuses` et, **uniquement si `metrics: true`**, les métriques Prometheus via `/metrics`. Son code `metrics/metrics.go` définit notamment la jauge de succès par endpoint et les compteurs de résultats. Requérir une observation récente avec labels déterministes (`group`, `name`, `type`, plus identifiant de service validé). `up == 1` pour le scrape ne prouve **pas** le succès de chaque sonde ; un résultat ancien ne prouve rien sur l'état actuel.

La fonction `evaluate_internal_probe_delegation` exige maintenant au moins une comparaison transport `TCP` avant le statut `candidate` ; des mesures `HTTP` seulement laissent la convergence **bloquée** (elles ne prouvent pas l'équivalence de transport). Ce garde-fou ne délègue ni ne désactive automatiquement aucune sonde.

Sécurité : exporter et API en LAN uniquement (authentification/ACL du proxy si partagé), délais courts, TLS vérifié, URLs/identifiants autorisés par catalogue, aucune redirection vers des adresses privées depuis une entrée non approuvée ; éviter les Docker sockets en écriture et les permissions élevées d'AutoKuma. Les identifiants/jetons restent dans Vaultwarden. Ne jamais confondre `HOMELAB_TRUSTED_CIDRS` et une authentification owner.

## Critères de convergence (non validés en production)

1. **Source d'autorité** : aligner IDs, cible/protocole et dépendances avec `nabla-compose` (pas avec un état découvert sans revue).
2. **Télémétrie** : Gatus `metrics: true`, scrape Prometheus privé, fenêtre de fraîcheur mesurée, pas de doublons ni de faux `UP` en absence de données ; exporter PostgreSQL / pfSense distingué du succès service.
3. **Comparabilité** : pour un check TCP interne, exiger une paire TCP/transport de même cible et constater `matched`, `mismatched`, `missing_gatus`, `conflicting_direct_ids`. Une preuve HTTP seule ne compte pas comme TCP.
4. **Fenêtre d'acceptation** : au moins trois fenêtres complètes de rotation et vérification manuelle LAN/staging. Tout résultat partiel, expiré ou incohérent bloque la délégation.
5. **Périmètre** : même après validation, ne réduire que les sondes internes redondantes ; préserver les vérifications externes, TLS, exposition, routes admin privées et tests spécifiques.
6. **Fail-safe** : si Gatus ou Prometheus deviennent indisponibles, afficher `unknown/unobserved`, réactiver les probes internes requis avant toute délégation future (aucune délégation automatique n'existe à ce jour).

**Vérification locale ciblée** (sur la branche et son environnement installé) :

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --no-sync pytest -q --noconftest \
  tests/unit/test_synthetic_probe_comparison.py \
  tests/unit/test_agent_quality_gate_contract.py
uv run --no-sync ruff check nabla/api/synthetic_probe_comparison.py \
  tests/unit/test_synthetic_probe_comparison.py \
  tests/unit/test_agent_quality_gate_contract.py
```

**État de preuve à la rédaction :** analyse statique des sources GitHub ; tests exact-HEAD, collecte Prometheus live et déploiement = **NOT_RUN**. Ne pas considérer les tests d'un SHA antérieur comme preuve.
