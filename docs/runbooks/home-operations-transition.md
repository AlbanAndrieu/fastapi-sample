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
- Les courbes sont **locales à l'onglet**, limitées à 24 points, sans persistance.
  Ne pas les présenter comme des historiques Prometheus.
- Le nuage de points CPU/HTTP requiert au moins **six paires** réelles,
  à 30 secondes au plus d'écart. Un coefficient de Pearson n'est affiché
  que si les deux variables présentent une variance mesurable.
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
  tests/unit/test_sensor_import_safety.py
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

**À différer** : historiques serveur Prometheus `query_range`, p95 de latence
HTTP et corrélation erreurs/CPU. Nécessitent une fenêtre, une politique
de fraîcheur et des limites de cardinalité validées avant ajout.

## Livraison légère de l'accueil

Le template `/` est un HTML autonome et n'hérite plus de `base.html`.
Il charge seulement des ressources CSS/JS locales, sans Chart.js,
Plotly, HTMX, DaisyUI ou Tailwind CDN. La réponse est `no-store`
et comporte une CSP limitant les scripts et connexions au même domaine,
avec `frame-ancestors 'none'`.
