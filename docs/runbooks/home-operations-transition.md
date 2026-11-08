# Transition du tableau de bord : capteurs fictifs → observabilité

## Décision

La racine `/` contenait une démo météorologique :
température, humidité, pression, corrélations et anomalies calculées sur
`SensorData`, ainsi qu'un formulaire de notes PostgreSQL. Ces valeurs
ne documentaient **aucune** propriété opérationnelle de FastAPI Sample.

Après migration, `/` devient `Operations Overview` :

| Ancien élément | Nouveau constat réel | Source / limite |
| --- | --- | --- |
| Température | CPU (cœurs) du conteneur FastAPI | cAdvisor → Prometheus ; pas un pourcentage sans quota |
| Humidité | Mémoire active (MiB) | cAdvisor → Prometheus ; pas la RAM libre du système |
| Pression | Débit réseau RX + TX (KiB/s) | cAdvisor → Prometheus ; pas la latence |
| Chronologie météo | Couverture des preuves de sondes | `health-board.homelab.probe_summary` ; fenêtres observées dans cet onglet |
| Diagramme d'état des capteurs | OK/WARN/FAIL/UNKNOWN | `/api/ui/services` ; pas de preuve fraîche = UNKNOWN |
| Corrélation météo | Mise en regard sondes, accès et exposition | `health-board.homelab.connection_matrix` et `sickz.checks.security_policy_status` |
| Anomalies fictives | Contrôles DNS/Tunnel/Access/TrueNAS/Prometheus | Catégories existantes ; aucune anomalie déduite sans preuve |
| Réactualisation via SSE synthétique | Lecture 30 s de caches serveur | Aucune nouvelle sonde unitaire par carte |
| Latence | Durée HTTP effective des sondes | `latency_ms` ; ce n'est **pas** le RTT TCP/ICMP |

Les anciennes mesures restent disponibles en **démo explicitement
signalée** sur `/demo/sensors` lorsque la fonctionnalité DB est active.
Les endpoints de démonstration ne sont pas supprimés pour éviter une rupture
d'intégration. La génération des 50 valeurs de capteur n'a plus lieu au
démarrage du processus.

## Frontières d'autorisation

1. L'affichage public ne lit que `/api/ui/services` et rend la distribution.
2. Le navigateur interroge `/api/ui/session` en mode same-origin.
3. Si `authenticated !== true`, aucun endpoint détaillé n'est demandé
    depuis la racine. Un lien mène à `/api?operator=1`.
4. Si la session est reconnue, la page lit les **caches** :
    `/api/health-board` et `/api/topology-telemetry`.
5. La protection serveur existante demeure l'autorité.
    Le client n'envoie aucun cookie ou clé dans une URL ou un stockage local.
6. Le serveur ne doit jamais faire confiance au seul JavaScript pour
    autoriser l'accès à ces endpoints ; revoir l'allowlist de lecture
    publique avant d'exposer la page sur un réseau non autorisé.

## Interprétation et diagnostic

- **0** est une mesure réelle et distincte de `null`/absent.
- Un scrape `up=1` n'atteste pas la santé applicative.
- Un 401/403 Cloudflare Access n'atteste pas l'état de l'origine.
- Une résolution DNS n'atteste ni HTTPS ni Tunnel.
- La courbe ne commence qu'après **deux snapshots datés distincts**.
- Les courbes **de preuves ponctuelles** sont locales à l'onglet et limitées
  à 24 points. Les courbes **CPU/mémoire/réseau/p95/Gatus** utilisent
  maintenant `query_range` depuis le serveur, avec 1 h, 24 h et 7 j
  (60 s, 300 s et 1 800 s de pas respectivement), 350 points maximum
  par série et interruption du trait si un intervalle manque.
- Le nuage de points CPU/p95 requiert au moins **six paires** réelles
  de l'historique Prometheus avec exactement le même horodatage. Un
  coefficient de Pearson n'est affiché que si les deux variables présentent
  une variance mesurable. La durée d'une sonde HTTP et le p95 des
  requêtes FastAPI ne sont pas la même mesure.
- Pour une étude de causalité ou une corrélation sur plus longue période,
  consulter les **mêmes fenêtres temporelles** de Prometheus (rate CPU,
  mémoire, débit, erreurs, latence) et Gatus. Ne pas déduire de causalité
  d'une coïncidence de courbes.

## Validation locale (sans CI ni déploiement)

```bash
node --check nabla/api/assets/home-operations-model.js
node --check nabla/api/assets/home-operations.js
node --test tests/js/home-operations-model.test.mjs
python -m pytest -q \
  tests/unit/test_home_operations_contract.py \
  tests/unit/test_app_factory.py \
  tests/unit/test_notes.py \
  tests/unit/test_lifespan.py \
  tests/unit/test_sensor_import_safety.py \
  tests/unit/test_home_metrics_history.py \
  tests/unit/test_home_history_route_auth.py \
  tests/unit/test_topology_telemetry.py
git diff --check master...HEAD
```

## Recette

- `/` en session anonyme : état public seulement, sans cartes sensibles.
- `/` en OWNER autorisé : trois séries cAdvisor et sonde HTTP si mesurées.
- Prometheus indisponible : CPU/mémoire/flux restent inconnus.
- `health-board` en attente ou périmé : aucun statut de sécurité vert.
- `/demo/sensors` : anciens graphiques étiquetés comme simulés, hors accueil.
- Mobile : ordre des cartes et affichage des statuts sans scroll horizontal.
- Contrôler les exports et le SHA réellement déployé sur TrueNAS et Cloud.

**Implémenté en code** : historique serveur `query_range` à fenêtres fixes,
p95 HTTP si `http_request_duration_seconds_bucket{job="fastapi_sample"}`
est collecté, et corrélation CPU/p95 sur les mêmes fenêtres. La disponibilité
Gatus requiert `nabla:service:synthetic_availability_ratio_5m` avec
`nabla_service_id=sample` ou `fastapi-sample`. Si les séries sont
absentes, la courbe et la valeur restent inconnues.

**À différer** : attribution réseau par flux, traces distribuées p95
par destination et analyse de causalité CPU/latence. Ces sujets
nécessitent une cardinalité, une instrumentation et une recette distinctes.

## Livraison légère de l'accueil

Le template `/` est un HTML autonome et n'hérite plus de `base.html`.
Il charge seulement des ressources CSS/JS locales, sans Chart.js,
Plotly, HTMX, DaisyUI ou Tailwind CDN. La réponse est `no-store`
et comporte une CSP limitant les scripts et connexions au même domaine,
avec `frame-ancestors 'none'`.


## Pulse TrueNAS en direct (08/11)

Constat du 8 novembre sur FastAPI Cloud : les sections CPU/mémoire/réseau
restaient vides, car elles dépendent de Prometheus (LAN uniquement :
`/api/home/metrics/history` répond `not_executed`, `/api/topology-telemetry`
`not_configured`). L'API TrueNAS, elle, est joignable et authentifiée depuis
le Cloud (observateur dédié). L'accueil propriétaire lit donc désormais
`GET /api/home/appliance/pulse` : un instantané **en direct** de l'appliance,
sans Prometheus, avec cache 30 s et échéance 8 s.

Appels middleware, tous en lecture seule et documentés, dans une seule session
authentifiée ; chacun est optionnel et son échec est classé (`errors`) sans
texte d'erreur :

| Méthode | Rôle TrueNAS | Signal |
| --- | --- | --- |
| `system.info` | `READONLY_ADMIN` | version, cœurs, charge 1/5/15 min, charge par cœur, uptime |
| `alert.list` | `ALERT_LIST_READ` | alertes actives par niveau, classe, texte sans HTML (160 car.) |
| `pool.query` | lecture | capacité, santé, fragmentation, scrub par pool |
| `interface.query` | lecture | interfaces physiques/LAG et état de lien |
| `app.query` | lecture | états des Apps (RUNNING/STOPPED/CRASHED/DEPLOYING) |
| `reporting.netdata_graphs` | `REPORTING_READ` | libellés d'axe (`vertical_label`) |
| `reporting.netdata_get_data` | `REPORTING_READ` | séries 1 h : `cpu`, `memory`, `interface` (liens physiques actifs) |

Les séries netdata ne sont converties que si leur légende est reconnue
(`idle` pour le CPU, `used`/`free` pour la mémoire, `received`/`sent` pour le
réseau) ; sinon la section indique `legend_unrecognized` avec la légende
observée, sans valeur inventée. Les pourcentages sont des ratios, donc
indépendants des unités netdata ; le débit réseau porte le libellé d'axe
renvoyé par TrueNAS.

**Interdépendances** (`impacts`) : associations calculées uniquement entre
signaux du même instantané — capacité du pool ↔ alertes stockage, santé des
pools, charge par cœur ↔ services, mémoire ↔ Apps `CRASHED`, flotte d'Apps ↔
alertes Apps, niveaux d'alertes, liens physiques inactifs. Chaque ligne porte
l'état `ok`/`warn`/`fail`, la preuve et les identifiants liés ; aucune
causalité n'est affirmée. `pressure_state` est le pire des états.

Recette : depuis une session OWNER, `GET /api/home/appliance/pulse` doit
répondre `state=observed` (ou `partial` avec `errors` listant les méthodes
refusées, à corriger par les rôles de la clé d'observation). Sans session :
refus. Tout paramètre de requête : 422. Les erreurs middleware n'apparaissent
que sous forme de classification (`stage:ExceptionType`).

## Conditions d'acceptation — TrueNAS et FastAPI Cloud

1. Sur TrueNAS : `FASTAPI_RUNTIME_MODE=homelab` et
    `HOMELAB_PROMETHEUS_URL` configurés pour un Prometheus de confiance.
2. Depuis une session OWNER autorisée, vérifier :
    `GET /api/home/metrics/history?window=1h`, puis `24h`, puis `7d`.
    Contrôler `model`, `state`, `step_seconds`, `series` et la durée.
3. Vérifier dans Prometheus la présence des métriques cAdvisor pour le
    conteneur Compose `sample` (ou l'un des noms prévus).
4. Confirmer l'instrumentation HTTP `http_request_duration_seconds_bucket`,
    sous le job `fastapi_sample` ; si absente, p95 doit rester inconnu.
5. Confirmer l'enregistrement `nabla:service:synthetic_availability_ratio_5m`
    pour le service Gatus correspondant ; une série manquante n'est pas 0 %.
6. Sans session OWNER, l'historique répond par un refus.
    La règle de lecture publique temporaire n'y donne pas accès.
7. En Cloud, le même endpoint ne doit jamais joindre Prometheus LAN ;
    son résultat est `not_executed` si appelé par une session autorisée.
8. Contrôler que `/` affiche la synthèse publique sans bloquer
    et que `/demo/sensors` reste une démonstration distincte.
9. Vérifier les cas 302/403 (Access), 429, timeout, série ambiguë
    et série périmée : jamais un statut sain inventé.
10. Vérifier les captures desktop/mobile (CSS autonome, sans CDN) et
    confirmer le SHA réellement déployé sur les deux plateformes.

**Limites de validation dans l'environnement d'édition :** le dépôt et les
connecteurs GitHub permettent les changements, mais pas une session TrueNAS
ou Prometheus local authentifiée. La vérification opérationnelle nécessite
une recette depuis le LAN. Aucun secret, pare-feu ni jeton n'est modifié.

Les paramètres de requête inattendus, notamment `query`, sont rejetés
avec HTTP 422 sur l'endpoint d'historique. Les requêtes sont prédéfinies,
en lecture seule, avec un cache de 120 secondes.
