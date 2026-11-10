# FastAPI Cloud — CPU, RAM et budget des sondes (10/11/2026)

## Données vérifiables

La console **FastAPI Cloud → application → Metrics** montre CPU (vCPU),
mémoire (bytes) et réplicas actifs ; le plan Pro ajoute trafic HTTP,
latence et ventilations par route. Les métriques sont moyennées entre
réplicas : un seul réplica peut atteindre sa limite avant la moyenne.

Documentation officielle :
- https://fastapicloud.com/docs/monitoring-and-performance/metrics/
- https://fastapicloud.com/docs/team-management/billing/usage-based-billing/

**Attention** : le modèle de coût documenté est essentiellement fondé sur
les **heures-réplicas**, pas sur la seule moyenne CPU. À ce jour, les
documents de la plateforme précisent que la facturation à l'usage n'est
pas encore active. Réduire le trafic et CPU aide la stabilité, mais n'est
pas une économie chiffrable sans les mesures du compte.

## Constat du code : origine de la charge

- Le health-board complet peut lancer **12 sondes publiques par vague**
  et des enrichissements DNS, HTTP, Cloudflare, TrueNAS, Prometheus et
  sécurité ; son délai maximum est **40 secondes**.
- Avant optimisation : cache health-board par défaut **30 secondes**,
  incluant sur le Cloud ; chaque nouvelle vague peut générer des sorties
  réseau et consommer du CPU.
- Chaque réplica contient son cache L1. Le L2 Redis des seuls noms publics
  ne constitue **pas** un cache partagé de la santé des sondes.
- Le serveur échantillonnait les jauges psutil CPU/RAM/RSS toutes les
  **5 secondes**, même sur les instances Cloud à faible capacité.

## Correctifs à déployer

| Budget | FastAPI Cloud | TrueNAS homelab |
| --- | --- | --- |
| Cache health-board par défaut | 180 s, configurable 60–600 | 30 s inchangé |
| Échec de reconstruction | backoff 90 s, configurable 15–300 | reprise existante |
| Refresh forcé / concurrent | au moins 30 s entre démarrages, single-flight | politique existante |
| Mesure psutil CPU/RAM/RSS | toutes les 30 s | toutes les 5 s |
| Rafraîchissement de l'accueil | toutes les 60 s après warm-up | 30 s |
| Sondes dans une vague | 12 max, pas d'augmentation | 12 max |

Ces seuils réduisent une **fréquence théorique** de refresh Cloud de
2 vagues/minute à environ 1 vague/3 min, soit environ **six fois moins
de reconstructions au régime de cache**. Ce n'est pas un gain CPU
mesuré ; le trafic réel dépend du nombre de workers, des échecs et
des requêtes OWNER. Les cinq étapes de warm-up UI restent actives :
elles ne peuvent pas contourner le budget serveur. Une absence de
preuve fraîche s'affiche comme `UNKNOWN`, jamais `OK` par défaut.

## Recette production : sans forcer de déploiement

1. Comparer le SHA GitHub avec le SHA réellement déployé.
2. Depuis la console FastAPI Cloud → **Metrics**, noter CPU moyen/max,
   mémoire moyenne/max et nombre de réplicas pour 24 h.
3. Depuis `/api/ui/services`, observer `pending`, `fresh` ou
   `stale` sans déclencher manuellement de rafraîchissements.
4. Observer les durées des tâches de refresh et l'absence de rafales
   de sondes. Comparer sur des fenêtres de trafic comparables.
5. Confirmer qu'aucune politique Cloudflare Access/OWNER n'a été
   desserrée et qu'aucune sonde LAN n'a été exécutée sur Cloud.
6. Mesurer les volumes sortants depuis la console lorsque disponibles,
   ainsi que la plage de réplicas (minimum 0 pour scale-to-zero si
   compatible avec vos besoins et votre plan).
7. Conserver le comportement TrueNAS des sondes à 30 s.

## Tests locaux

```bash
python -m pytest -q \
  tests/unit/test_cloud_runtime_budget.py \
  tests/unit/test_health_board_cache.py \
  tests/unit/test_health_runtime_settings.py \
  tests/unit/test_ui_public_services.py
node --check nabla/api/assets/home-operations.js
node --test tests/js/home-operations-model.test.mjs \
  tests/js/home-operations-warmup.test.mjs
git diff --check master...HEAD
```

Les limites CPU/RAM et le coût réel ne peuvent pas être inférés d'un
code source, du succès d'une CI ni de la disponibilité HTTP. Ce rapport
ne prétend pas avoir accès à la console privée de l'application.

### Polling et scale-to-zero (économie de réplicas)

Le scale-to-zero est activé par défaut sur FastAPI Cloud :
https://fastapicloud.com/docs/builds-and-deployments/how-it-works/

Le navigateur effectue un premier chargement, puis un polling Cloud à
60 secondes. **Après 5 minutes sans interaction dans l'onglet Cloud**,
les lectures périodiques et les retries courts sont suspendus. Un
nouveau clic/touche ou le retour vers l'onglet relance la vérification.
Le polling sur TrueNAS reste à 30 secondes, sans mise en pause sur
inactivité au premier plan. Les contrôles utilisateur « Actualiser »
restent explicites et possibles.

Cette règle aide à permettre le passage à zéro réplica pour un onglet
laissé ouvert, mais ne garantit pas à elle seule une économie : d'autres
visiteurs, probes, crons et réglages de réplica minimum peuvent encore
maintenir l'application active. Aucun changement de scale/autoscaling
n'est effectué par ce code.
