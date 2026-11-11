# FastAPI Cloud — budget CPU, mémoire et réseau (09/11/2026)

## Périmètre

Cible : `https://fastapi-sample.fastapicloud.dev`, **pas Vercel**.
FastAPI Cloud est un observateur WAN, **pas** un administrateur du LAN.
La plateforme Native Metrics mesure le CPU et la mémoire **par réplica** ;
`/api/runtime/resources` donne un échantillon **du processus Python**
seulement. Ne pas convertir ce dernier en facture ou en CPU total de
la plateforme.

## Constat et impact

1. L'ancienne lecture anonyme `/api/ui/services` pouvait déclencher
    `get_health_board_snapshot` : création d'une tâche unique mais
    potentiellement longue (jusqu'à 40 s), avec fan-out vers TrueNAS,
    Cloudflare, Prometheus et les analyses de politique.
2. Sur le runtime Cloud, une page ouverte lançait `/` toutes les 30 s.
    Le mode avancé `/api?ui_full=1` pouvait sonder à 5 s en rafraîchissement
    et 30 s au repos. Cela maintient du trafic et retarde le scale-to-zero.
3. Les workers de démarrage exécutaient une boucle `psutil` (5 s),
    un consommateur Redis pub/sub et un heartbeat de topologie (30 s)
    même si aucun diagnostic n'était consulté.

## Politique économique implémentée

| Flux | FastAPI Cloud | TrueNAS |
| --- | --- | --- |
| `/api/ui/services` anonyme | Lecture passive du cache agrégé, **aucun nouveau fan-out** | Contrat précédent conservé |
| Diagnostics OWNER `/api/health-board` | Autorisés, TTL minimum 180 s ; backoff 180 s après échec | TTL configurable existant |
| Accueil `/` anonyme | Lecture à l'ouverture, au retour et sur clic ; **pas de polling permanent** | Polling 30 s |
| Accueil `/` OWNER | Polling 180 s | Polling 30 s |
| Mode complet `/api?ui_full=1`, public readonly | Lecture initiale sans ticker permanent | Polling existant |
| Mode complet `/api?ui_full=1`, OWNER | Polling 180 s, 15 s en refresh, 180 s sur erreur | 30 s, 5 s, 60 s |
| Workers idle `psutil` / Redis / heartbeat | Inactifs par défaut | Actifs selon les fonctions |
| Gauges CPU et RAM du worker sans mesures | NaN (**inconnu**, pas zéro) | Mesures effectives |
| `/api/runtime/resources` | Lecture à la demande OWNER | Lecture à la demande OWNER |

Le seul retry automatique à froid sur l'accueil Cloud est prévu
**15 s après la première lecture** ; sans preuve, le statut reste
`UNKNOWN`. Une visite publique ne suffit plus à lancer les sondes
détaillées. C'est un arbitrage volontaire en faveur du budget.
Les diagnostics à jour sont déclenchés par un appel OWNER autorisé ou
un collecteur externe avec son propre budget.

### Options d'activation

Par défaut, sur FastAPI Cloud :

```dotenv
FASTAPI_CLOUD_PUBLIC_DEEP_PROBES_ENABLED=false
FASTAPI_CLOUD_BACKGROUND_WORKERS_ENABLED=false
```

La première option autorise de nouveau les diagnostics profonds depuis
l'accueil anonyme et peut empêcher une mise au repos sous trafic.
La seconde réactive les trois boucles résidentes. **Ne pas activer**
par commodité ; mesurer d'abord. Les valeurs par défaut n'ont aucun
effet sur le fonctionnement TrueNAS.

`FASTAPICLOUD_DEPLOYMENT_ID` est le marqueur d'instance injecté
par la plateforme. Le code s'en sert pour reconnaître le runtime
même si une configuration ancienne comporte `FASTAPI_ENV=development`.
L'identifiant n'est pas copié dans les DTO publics.

## Contrôle des ressources

Sur le tableau de bord FastAPI Cloud : choisir l'application,
puis **Metrics → Application Health**. Vérifier le CPU en vCPU, la
mémoire en octets et le nombre de réplicas sur une période d'une journée.

Le dashboard permet le suivi par réplica. Un Nano dispose de 0,1 vCPU
et 500 MiB de RAM selon la documentation publiée. Examiner aussi les
dépassements individuels même si la moyenne est faible.

Pour une lecture diagnostique sans sampler permanent :

```text
GET /api/runtime/resources
X-Diagnostics-Key: <configured owner credential>
```

L'endpoint renvoie `rss_bytes`, `process_cpu_seconds_total` et
`threads`. **CPU time ≠ CPU%**, **RSS ≠ provisioned memory** et aucune
information de coût/hôte n'est déduite. Réponse sans cache, accès
OWNER renforcé dans la route et la politique des accès.

### Validation avant/après (mêmes fenêtres et trafic)

- Relever **au moins 30 minutes** avant et après le même profil de trafic.
- Noter CPU vCPU moyen/max, mémoire moyenne/max, réplicas, requêtes et
  latence, ainsi que les erreurs et redémarrages.
- Vérifier qu'un onglet anonyme Cloud laissé ouvert pendant plus de
  10 minutes ne déclenche **aucun polling périodique**.
- Vérifier que `/api/ui/services` est public et ne démarre pas
  `health-board-refresh` sur Cloud.
- Sur une vraie session OWNER, vérifier que les sondes restent
  accessibles et limitées à la nouvelle cadence.
- Comparer FastAPI Cloud, TrueNAS et navigateur séparément ;
  ne pas attribuer des métriques de Vercel à FastAPI Cloud.

L'absence de métriques publiques en lecture distante n'est pas une
preuve de faible CPU. Les compteurs de facturation ne sont pas exposés
sur les endpoints applicatifs : lire le dashboard authentifié.

## Tests locaux

```bash
node --check nabla/api/assets/home-cost-policy.js
node --check nabla/api/assets/home-operations.js
node --check nabla/api/assets/api-health-controller.js
node --test tests/js/home-cost-policy.test.mjs tests/js/cloud-api-cost-guard.test.mjs \
  tests/js/home-public-cache.test.mjs tests/js/home-operations-model.test.mjs \
  tests/js/home-operations-warmup.test.mjs
python -m pytest -q \
  tests/unit/test_cloud_runtime_cost_guard.py \
  tests/unit/test_runtime_cost_observer.py \
  tests/unit/test_health_board_cache.py \
  tests/unit/test_ui_public_services.py \
  tests/unit/test_runtime_environment.py \
  tests/unit/test_lifespan.py \
  tests/unit/test_cloud_ui_outage_resilience.py
git diff --check master...HEAD
```

## Statut

**CODED / NOT DEPLOYED** — aucune mesure vCPU/RSS réelle ni
confirmation du SHA déployé obtenue depuis cet environnement.
La plateforme conserve la propriété du déploiement :
ne pas lancer `fastapi deploy` dans une CI supplémentaire.

## Sources

- https://fastapicloud.com/docs/monitoring-and-performance/metrics/
- https://fastapicloud.com/docs/advanced-features/autoscaling/
- https://fastapicloud.com/docs/team-management/billing/usage-based-billing/

## Correction UI et budget Hobby — 10 novembre 2026

- La page `/api?operator=1&ui_full=1` importe explicitement le classifieur
  `isTrueNasExposureCheck` du module de classification partagé.
- Le drill-down TrueNAS s'aligne désormais sur le **début** du panneau
  (`scrollIntoView({block:"start"})`) ; le schéma des protocoles reste
  défilable horizontalement dans un conteneur borné.
- Le panneau **FastAPI runtime** en mode Cloud présente les enveloppes
  Hobby **prévues** (180 heures-réplicas Nano, 5 Go sortants, 500 minutes
  de build par période). Les compteurs sont communs à l'équipe et
  **ne sont pas** les consommations de l'application.
- L'endpoint protégé `GET /api/runtime/resources` est appelé **une fois
  sur action explicite OWNER**, sans rafraîchissement automatique.
  Sa mémoire RSS de processus est comparée à la référence Nano de 500 MiB :
  seuil d'information à 80 %, seuil critique à 100 %. Ce signal n'est
  ni la mémoire totale du réplica ni une alerte de dépassement de quota.
- Tant qu'il n'existe pas de source fiable pour les totaux de consommation
  de l'équipe, les indicateurs de quota restent **unavailable**, et
  aucune alerte de dépassement de quota mensuel n'est affichée.
- La documentation officielle signale que l'usage n'est pas encore
  facturé à la consommation ; aucune API de quota authentifiée exploitable
  depuis ce frontend n'a été attestée.

Tests du changement (sans Actions) :

```bash
node --check nabla/api/assets/api-cloud-budget.js
node --check nabla/api/assets/api-sickz.js
node --test tests/js/api-cloud-budget.test.mjs
python -m pytest -q tests/unit/test_api_service_group_assets.py \
  tests/unit/test_health_ui_operator_followup.py \
  tests/unit/test_runtime_ui_contract.py
```

Recette à faire sur le SHA **déployé** : afficher la page Cloud avancée sans
`ReferenceError` ; ouvrir le lien TrueNAS à 375 px et 1280 px de large ;
confirmer que le titre reste visible et que le schéma défile sans débordement
global ; ouvrir le budget Hobby, valider que la mesure est refusée hors OWNER
et n'induit aucune requête périodique. Mesurer les véritables valeurs CPU,
mémoire et réplicas dans la console Cloud (Metrics).

Sources :
https://fastapicloud.com/docs/team-management/billing/
https://fastapicloud.com/docs/team-management/billing/usage-based-billing/
https://fastapicloud.com/docs/monitoring-and-performance/metrics/

## Profilers continus et cadence OWNER — 11 novembre 2026

Le navigateur Cloud affichait une politique OWNER de **180 secondes**,
mais `home-operations.js` utilisait un timer codé à **60 secondes**.
Le timer consomme désormais la valeur unique de `home-cost-policy.js`.
Pour un onglet OWNER actif, le maximum théorique d'actualisations
périodiques passe de 60 à **20 par heure** (hors chargement initial,
clic manuel, changement de fenêtre, reprise de visibilité et warm-up).
Ce n'est pas une mesure de CPU, mais une réduction déterministe des
appels périodiques, à vérifier dans l'onglet Network.

Les profilers Pyroscope et Datadog, qui échantillonnent continuellement
le processus et peuvent ralentir le cold-start, sont maintenant **inactifs
par défaut sur FastAPI Cloud**. L'instrumentation native, Sentry et
les endpoints de diagnostics existants restent accessibles.
Sur TrueNAS les profilers ne changent pas.

Pour activer temporairement ces profilers lors d'un incident :

```dotenv
FASTAPI_CLOUD_PROFILING_ENABLED=true
```

Ne pas activer les profilers sur une offre Nano en fonctionnement normal ;
réactiver seulement pour une fenêtre de diagnostic et mesurer
l'évolution CPU/RSS dans **Dashboard → App → Metrics**.

> **Mesures réelles de consommation :** le tableau privé de FastAPI Cloud
> présente CPU vCPU, mémoire (bytes) et réplicas. Les valeurs ne peuvent pas
> être déduites du code ni de `/api/runtime/resources`. À ce jour,
> l'API publique de consommation de l'équipe n'est pas disponible et les
> totaux d'usage du tableau de facturation ne sont pas encore affichés,
> selon la documentation du fournisseur.

### Validation spécifique

```bash
node --test tests/js/home-cost-policy.test.mjs
python -m pytest -q tests/unit/test_cloud_runtime_cost_guard.py
```

Après déploiement, comparer sur deux fenêtres identiques avec un OWNER
connecté et l'onglet visible : appels `/api/ui/services` par heure,
CPU vCPU, mémoire, réplicas, éventuels OOM/restarts.
Ne pas prétendre à un gain CPU chiffré sans les métriques fournisseur.

## Lecture cgroup du conteneur — 11 novembre 2026

L'endpoint OWNER **déjà existant** `GET /api/runtime/resources`,
consulté uniquement sur clic, joint maintenant un objet `cgroup` :

- `memory_current_bytes`, `memory_limit_bytes`, `memory_limit_percent`
  lorsque Linux cgroup v2 publie `memory.current` et `memory.max` ;
- `cpu_quota_cores` depuis `cpu.max`, `cpu_usage_seconds_total`
  depuis `cpu.stat` (compteur cumulé, **pas un pourcentage CPU**) ;
- `oom_kill_count` depuis `memory.events`, compteur cumulé.

Chaque fichier lu est strictement allowlisté et plafonné à 4 Kio.
Aucun parcours du système de fichiers, aucune interrogation réseau,
aucun échantillonnage permanent. Toute valeur absente, illimitée ou
invalide reste `null`, jamais zéro simulé.

Le panneau OWNER privilégie une consommation mémoire **réellement
rapportée à la limite cgroup** lorsque ces deux valeurs sont disponibles,
avec avertissement à 80 % et danger à 100 %. Il affiche séparément le RSS
du processus Python. Sinon, il conserve son comparatif indicatif au Nano
500 MiB, sans le présenter comme la mesure du conteneur.

**Limite de preuve :** `memory.current` inclut les charges mémoire du
cgroup et peut différer de la métrique provider ; `cpu.stat` est cumulatif
et ne donne pas une moyenne vCPU sans deux horodatages. Ces mesures ne
représentent ni la mémoire facturée, ni les heures-réplicas, ni les
totaux d'équipe. Les vraies courbes CPU/mémoire/réplicas sont dans
**FastAPI Cloud → Application → Metrics**.

### Réglage de sécurité budgétaire (manuel, sans application automatique)

Sur Hobby, le minimum de réplicas est fixé à zéro par la plateforme.
Si une seule instance suffit, limiter le maximum à **1** dans
**Application → Scaling** réduit le plafond de ressources simultanées,
au prix d'une baisse de capacité sous charge. Ce réglage ne garantit
pas un budget mensuel et n'a pas été modifié par cette PR.

Valider avant/après sur la même fenêtre 30 minutes, avec un trafic
représentatif : pic et moyenne vCPU, RAM, réplicas, OOM et volume de
requêtes. Les totaux mensuels partagés ne sont pas disponibles dans le
tableau de facturation au moment de cette livraison.
