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
