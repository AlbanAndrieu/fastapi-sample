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

Sources vérifiables : [Gatus go.mod](https://github.com/TwiN/gatus/blob/master/go.mod), [Gatus metrics](https://github.com/TwiN/gatus/blob/master/metrics/metrics.go), [Gatus README](https://github.com/TwiN/gatus/blob/master/README.md), [AutoKuma Cargo.toml](https://github.com/BigBoot/AutoKuma/blob/master/Cargo.toml), [AutoKuma client](https://github.com/BigBoot/AutoKuma/blob/master/kuma-client/Cargo.toml), [Healthchecks requirements](https://github.com/healthchecks/healthchecks/blob/master/requirements.txt), [Cabot requirements](https://github.com/arachnys/cabot/blob/master/requirements.txt). Comparer les versions installées séparément.

## Code existant et dépendances à mutualiser

- `nabla/api/homelab_probe_runner.py` : HTTP via `httpx.AsyncClient`, TCP via `anyio.connect_tcp` et contrôles DNS via `nabla/api/dns_probe.py` (`dnspython`). Conserver uniquement les cas spécifiques et l'observation outside-in lorsqu'ils ne sont pas déjà couverts depuis le même point de vue.
- `nabla/api/prometheus_query.py` : requêtes PromQL instantanées fixes et validation stricte des résultats. **Réutiliser ce client** plutôt qu'ajouter un SDK Gatus tiers, un proxy ou un scraping public.
- `nabla/api/synthetic_probe_comparison.py` : observations `gatus_via_prometheus`, comparaison des seuls transports compatibles et décision `shadow_only`. Les preuves `HTTP`/ `HTTPS` restent des observations applicatives distinctes des preuves `TCP`.
- `nabla/api/homelab_dependency_health.py` : propagation des défaillances de dépendances de topologie, à garder distincte d'une absence de métriques.
- `nabla/api/data/homelab-services.json` : catalogue projet ; aligner les IDs avec la source d'autorité `nabla-compose`, pas avec des labels arbitraires de Prometheus. Ne pas publier les chemins internes, adresses, jetons ou alertes privées.

**Ne pas ajouter de dépendance Python de supervision dans `pyproject.toml` pour ce seul objectif** : `httpx`, `anyio`, `dnspython`, `prometheus-client` et Pydantic y sont déjà présents. Ajouter Healthchecks signifierait déployer et maintenir une seconde application Django/DB pour un cas d'usage différent.

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
