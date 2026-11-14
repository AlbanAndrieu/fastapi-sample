# H05 — Historique OWNER et reprise intelligente des sondes

Le résumé **PUBLIC** de l'UI conserve déjà les dernières observations pendant
au plus sept jours dans le navigateur. Cette donnée est grise/historique et
n'est jamais une preuve de santé actuelle.

Le panneau avancé OWNER dispose maintenant d'une mémoire **serveur opt-in**,
distincte de la fenêtre mémoire /api/health-board. Il garde seulement
`id`, `scope` (`public` ou `internal`), `state` et
`observedAt` pour chaque sonde directe réellement exécutée. Aucune adresse
privée, URL, cible, credential, nom de conteneur ou JSON brut n'est persistant.
Un état `DENIED`/`NOT_RUN`, une preuve `memory` ou une sonde expirée
ne peuvent pas être enregistrés comme nouvelle observation.

## Activation sur un runtime autorisé

Configurer côté serveur, pour **chaque environnement séparément** :

```dotenv
HOMELAB_OWNER_HISTORY_REDIS_ENABLED=true
HOMELAB_OWNER_HISTORY_NAMESPACE=truenas_dev
```

Pour Cloud, utiliser une autre valeur telle que `cloud_prod`. Le suffixe
Redis intègre aussi un hash du runtime et du domaine. L'activation reste
désactivée par défaut, échoue fermée sans namespace explicite, et n'oblige
pas à déployer une nouvelle instance Redis.

Le hash Redis a une expiration de sept jours, conservée atomiquement avec
l'écriture via `MULTI/EXEC`. Chaque sonde se trouve dans un champ distinct,
pour préserver les observations des autres vagues et workers. Les valeurs
individuelles sont revalidées à la lecture et exclues après sept jours.

## Sécurité et interface

- `GET /api/health-board/last-known` répond **403** sans vérification de
  la source réseau et du cookie signé OWNER ; l'accès public en lecture seule
  ne suffit pas. Réponse `Cache-Control: no-store`, sans indexation.
- À l'ouverture du tableau de bord détaillé, une requête bornée (2,2 s)
  lit cette mémoire sans déclencher de sondes.
- Le panneau natif `details` présente les états **historiques** avec âge ;
  aucun badge vert ne provient de ce cache. Il disparaît lorsqu'une vue
  de services fraîche et confirmée est disponible.
- Aucune persistance OWNER dans `localStorage` ou `sessionStorage`.
  Les échecs Redis sont `unavailable` et n'interrompent pas le tableau.

## Recette non encore exécutée

1. Déployer la PR fusionnée avec un SHA identifiable.
2. Activer Redis opt-in et créer au moins une observation directe.
3. Vérifier que la reprise après redémarrage ou quelques heures réaffiche
    les données uniquement après nouvelle authentification OWNER.
4. Vérifier les réponses anonymes 403, la source Cloud/TrueNAS, les TTL,
    l'absence de secrets Redis et les transitions `STALE`/`NO_SAMPLE`.
5. Mesurer le coût Redis et le budget Cloud avant `ACCEPTED`.

Ce premier lot n'archive pas les métriques Gatus/Prometheus ni les
composants TrueNAS non issus d'une preuve directe : leur provenance,
identité `entityRef` et fenêtre de fraîcheur restent à intégrer dans
H05/F03+F09. Le retrait du catalogue legacy relève ensuite de H17/F11.
