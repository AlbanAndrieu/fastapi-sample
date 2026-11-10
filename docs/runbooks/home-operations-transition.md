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

## Démarrage à froid Cloud et stratégie de cache (09/11/2026)

Lorsque le tableau `health-board` d'un nouveau worker n'a pas de données,
`/api/ui/services` peut fournir `boardState=pending` très rapidement :
le tableau de bord démarre son rafraîchissement en arrière-plan. Le
premier clic manuel ne doit pas être nécessaire pour voir les mesures
publiques dès que l'agrégat devient frais.

**Comportement de `/` :**

1. Au chargement, lire éventuellement `sessionStorage` pour afficher
    **uniquement les noms et catégories publics**, tous `UNKNOWN`.
2. Lancer immédiatement `/api/ui/services` et `/api/ui/session`
    en parallèle, mais afficher les cartes dès la réponse du catalogue,
    sans attendre la vérification de session.
3. Lorsque le résultat est `pending` ou `stale`, relire automatiquement
    après **2, 4, 8, 15 et 30 secondes**, puis revenir à l'intervalle
    habituel de **30 secondes**. Les onglets masqués ne sondent pas.
4. Une réponse publique `401/403/404` efface le cache de session ; aucun
    ancien nom n'est affiché comme preuve autorisée, et aucune tempête
    de retries n'est déclenchée.
5. Si le réseau tombe, un ancien inventaire public peut rester visible,
    mais **jamais** ses anciens états ou ses diagnostics propriétaires.

| Couche | Stockage | TTL / politique | Contenu |
| --- | --- | --- | --- |
| L0 navigateur | `sessionStorage` | 5 min, onglet courant ; `fetch` reste `no-store` | Noms et catégories publics seulement ; toujours `UNKNOWN` |
| L1 catalogue Backstage | Mémoire par worker | 5 min | Catalogue de référence déjà validé |
| L1 health-board | Mémoire par worker | TTL configuré ; calcul asynchrone | Sondes et preuves ; non persistées dans le navigateur |
| L1 topologie | Mémoire par worker | 15 s | CPU, mémoire, débit ponctuels |
| L1 historiques | Mémoire par worker | 120 s | `query_range` OWNER ; non persistant côté navigateur |
| L2 Redis annuaire (nouveau) | Redis partagé **opt-in** | 5 min | Seulement noms/catégories publics, statuts `UNKNOWN` |
| L2 Redis preuves (existant) | Redis partagé **opt-in** | Selon fenêtre de preuves | Observations de sondes publiques filtrées, jamais LAN |

L'annuaire L2 Redis ne remplace pas le catalogue de référence. Il n'est
consulté que si les données Backstage sont indisponibles ou bloquées par
le backoff et que le health-board **n'est pas frais**. Dès qu'un agrégat
frais existe, les données locales validées ont priorité.

### Activer Redis L2 de l'annuaire si un Redis autorisé est disponible

Configuration facultative côté serveur uniquement :

```dotenv
NABLA_PUBLIC_DIRECTORY_REDIS_ENABLED=true
NABLA_PUBLIC_DIRECTORY_REDIS_NAMESPACE=fastapi-cloud-prod
# REDIS_URL est fourni par le gestionnaire de secrets du runtime.
```

Un espace de noms explicite et distinct est obligatoire par environnement.
En l'absence de Redis joignable ou de configuration, le système retombe
sur l'inventaire local. Le client Redis est importé à la demande, les
échecs sont bornés à 150 ms et ne bloquent ni le chargement ni le démarrage.
Ne **jamais** mettre `REDIS_URL`, les clés, la session OWNER ou les
informations TrueNAS/Cloudflare dans `sessionStorage` ou `localStorage`.

### Recette spécifique au bouton « Actualiser »

- Vider l'onglet et ouvrir `/` sans appuyer sur Actualiser :
  l'inventaire public doit apparaître automatiquement.
- Simuler `pending` pendant le warm-up : les états doivent rester
  `UNKNOWN`, puis changer sans clic quand l'origine devient `fresh`.
- Recharger l'onglet avec le cache de session valide : inventaire
  immédiat, statuts inconnus jusqu'à la nouvelle réponse réseau.
- Simuler 403/404 : l'inventaire de session est effacé.
- Bloquer `sessionStorage` et Redis : aucun plantage.
- Ouvrir un onglet masqué : pas de rafraîchissement agressif.
- Tester deux workers avec le même Redis, mais des namespaces distincts :
  aucun mélange des catalogues ni des preuves.
- Sur FastAPI Cloud, vérifier les réponses de
  `/api/ui/services`, `/api/ui/session` et la console navigateur.
  Un agrégat Cloud dépourvu de sondes LAN doit rester `UNKNOWN`,
  pas `FAIL` par déduction.

### Validation locale

```bash
node --check nabla/api/assets/home-public-cache.js
node --check nabla/api/assets/home-operations.js
node --test tests/js/home-public-cache.test.mjs tests/js/home-operations-model.test.mjs
python -m pytest -q \
  tests/unit/test_ui_public_directory_redis.py \
  tests/unit/test_ui_public_services.py \
  tests/unit/test_home_operations_contract.py
git diff --check master...HEAD
```

**Contrainte de disponibilité :** sur un hébergement qui suspend ses
workers après la réponse HTTP, une tâche de warm-up lancée en arrière-plan
peut ne pas finir. Le cache Redis des **noms** ne transforme pas cette
limitation en sondes réelles. Elle nécessite une collecte planifiée ou
une source d'évidence partagée, authentifiée et explicitement
configurée. Ne pas modifier les règles d'accès pour la contourner.


## Comparaison graphique des ressources (9 novembre 2026)

L'accueil OWNER présente aussi une **mosaïque des sondes observées** :
jusqu'à 80 tuiles réelles triées par gravité (FAIL/WARN/UNKNOWN/OK),
avec hachures pour la preuve périmée. Les slots du catalogue sans
résultat ne sont pas fabriqués ; le nombre de sondes affichées reste
distinct de la couverture éligible. Chaque tuile possède un nom et un
état accessibles au lecteur d'écran. Les points historiques conservent
la différence entre absence de preuve et panne confirmée.

L'accueil OWNER ajoute un classement horizontal **des huit conteneurs
les plus consommateurs** avec sélection CPU (cœurs utilisés), mémoire
active (MiB), système de fichiers conteneur (MiB) ou réseau RX + TX
(KiB/s). La barre est **relative au maximum de l'échantillon**, jamais
un pourcentage de capacité hôte/quota. Les données sont tirées de
`/api/topology-telemetry`, déjà interrogé par OWNER : aucun fetch
Prometheus supplémentaire n'est réalisé par le navigateur.

La nouvelle requête serveur `container_fs_usage_bytes` (cAdvisor)
est **facultative** et calculée par `max by (compose_service)` pour
éviter le double comptage de plusieurs devices par conteneur. Elle
n'inclut **pas** les datasets ZFS, snapshots, PVC, volumes ni la
taille des images Docker. Leur occupation devra être ajoutée par
l'inventaire TrueNAS/ZFS, avec provenance séparée et contrôles d'accès.
Une mesure manquante s'affiche « inconnue », jamais « 0 » ; un zéro
observé demeure 0. Le graphique refuse les échantillons périmés.

Le panneau flux réseau affiche uniquement le débit agrégé pfSense
exposé par l'enregistrement Prometheus/collecteur Akvorado, avec
l'état de confirmation du collecteur si disponible. Le RX/TX cAdvisor
est par conteneur, **pas** par paire source/destination ; aucune
épaisseur d'arête n'est inventée. Une attribution future exige des
flux IPFIX associés à des identités réseau stables (`entityRef`),
puis des fenêtres temporelles cohérentes et un budget de cardinalité.

**Confidentialité** : classement, noms et flux sont sous
`home-operator-detail` et le navigateur ne charge pas la télémétrie
sans session `authenticated === true` ; aucune réponse OWNER n'est
stockée dans `sessionStorage`.

Contrôles locaux :

```bash
node --check nabla/api/assets/home-operations.js
node --check nabla/api/assets/home-operations-model.js
node --test tests/js/home-operations-model.test.mjs
python -m pytest -q tests/unit/test_home_operations_contract.py tests/unit/test_topology_telemetry.py
```

Références ergonomiques : Grafana [Node graph](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/visualizations/node-graph/),
[Docker monitoring cAdvisor](https://grafana.com/grafana/dashboards/15798-docker-monitoring/),
[Netdata metrics](https://learn.netdata.cloud/docs/dashboards-and-charts/tabs/metrics),
[conventions Prometheus](https://prometheus.io/docs/practices/naming/).

**Correction d'autorisation (9/11)** : la route `GET /api/topology-telemetry`
impose maintenant une session OWNER vérifiée **par le serveur** avant
toute requête Prometheus ; elle répond 403 et `Cache-Control: private,
no-store` sans privilège, même si le JavaScript est contourné.
La page `/api/topology` conserve le rendu du graphe déclaratif public,
mais les métriques détaillées restent privées.
