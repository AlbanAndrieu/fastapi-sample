# Diagnostics des connexions — FastAPI Sample TrueNAS / Cloud

## Périmètre et sources

La vue **Homelab probe fan-out → Infrastructure connections** affiche des
constats indépendants, et **non** une disponibilité globale :

| Connexion | Source | Interprétation |
| --- | --- | --- |
| API TrueNAS | WebSocket API observer | Authentification et méthodes de gestion ; un refus ne prouve pas un hôte arrêté |
| Application FastAPI sur TrueNAS | App/containers `sample` ou `fastapi-sample` + résultats de sondes publiques/LAN | Runtime, HTTP/HTTPS et LAN séparés ; un scrape exporter UP ne les remplace pas |
| HTTPS/TCP TrueNAS | Sondes directes, HAProxy/WAN selon le runtime | Transport distinct de l'API et du runtime applicatif |
| Prometheus API | Requête PromQL fixe depuis TrueNAS | Succès de requête, indépendamment des enregistrements disponibles |
| FastAPI Sample / TrueNAS / Gatus / Cloudflare exporter | Règles Prometheus | UP = scraping réussi, PAS un service applicatif sain |
| Tunnel / Access | Cloudflare API déjà observée | Inventaire/gestion confirmé, PAS santé de chaque route |
| `sample.albandrieu.com` et `fastapi-sample.fastapicloud.dev` | Cloudflare DoH public, requête A | Résolution **récursive**, PAS configuration autoritaire de la zone |
| FastAPI Cloud | GET `/api/ui/session` en HTTPS depuis TrueNAS | JSON anonyme cohérent = API atteinte ; 302/401/403 = protection ou refus |

Les sondes externes supplémentaires sont **uniquement** exécutées lorsque
`FASTAPI_RUNTIME_MODE=homelab` est explicitement configuré.
Le runtime Cloud **ne tente aucune connexion LAN**. Les trois vérifications
publiques sont concurrentes, avec 2,5 s maximum par requête et 3 s maximum
pour l'ensemble, et mises en cache en mémoire pendant 90 secondes.

Les états inconnus (`unknown`, `not_executed`) n'indiquent pas une panne.
Une résolution DNS correcte, un tunnel dans l'inventaire ou un scrape 1
ne prouvent jamais la disponibilité de l'origine.

## Vérification de configuration TrueNAS (sans secret affiché)

1. Vérifier `FASTAPI_RUNTIME_MODE=homelab` pour la seule instance TrueNAS.
2. Vérifier `HOMELAB_PROMETHEUS_URL` et `HOMELAB_PROMETHEUS_TIMEOUT_SECONDS`.
   Privilégier l'URL HTTP du Prometheus de confiance sur LAN.
3. Si Prometheus est accessible par HTTPS via Cloudflare Access, vérifier
   `HOMELAB_PROMETHEUS_CF_ACCESS_CLIENT_ID` et
   `HOMELAB_PROMETHEUS_CF_ACCESS_CLIENT_SECRET`.
   Le code ne transmet ces en-têtes qu'au domaine épinglé
   `prometheus.albandrieu.com:443`.
4. Vérifier `TRUENAS_API_USERNAME` et `TRUENAS_API_KEY` depuis le magasin de
   secrets, ainsi que `TRUENAS_LAN_HOST` et `TRUENAS_LAN_PORT`.
   Ne pas copier les secrets dans une issue ou un rapport.
5. Vérifier les variables de lecture seule `CLOUDFLARE_ACCOUNT_ID` et
   `CLOUDFLARE_API_TOKEN` pour l'inventaire Tunnel/Access.
6. Relever `/api/health-board` depuis la session autorisée ;
   examiner `homelab.connection_matrix.rows`, `platform_metrics.error_kind`
   et `platform_metrics.exporter_jobs`. Le premier appel peut renvoyer
   `state=pending` : attendre un instant puis relire le cache.
7. Contrôler les journaux de l'instance TrueNAS, Gatus et les cibles
   `up{job="fastapi_sample"}`, `up{job="truenas_node"}` et
   `up{job="cloudflare_exporter"}` dans Prometheus, depuis le LAN autorisé.
   Comparer l'horodatage et la fraîcheur des séries.

## Recette d'acceptation

- `PROMETHEUS` : distinguer absence d'URL, refus 401/403, redirection
  Cloudflare, HTTP 429, timeout, échec TCP, réponse JSON incorrecte et scrape DOWN.
- `TRUENAS` : vérifier indépendamment TCP, HTTPS, API et disponibilité du
  conteneur FastAPI Sample sur `:8091`.
- `CLOUDFLARE` : contrôler l'inventaire Tunnel/Access et la résolution DNS,
  puis un vrai accès authentifié à une origine autorisée avant de conclure.
- `FASTAPI CLOUD` : l'observation de `/api/ui/session` n'authentifie aucun
  accès OWNER ; comparer la version réellement déployée.

**À différer :** exporter la santé LAN depuis TrueNAS vers Cloud via une voie
signée et autorisée. Ne pas publier les IP LAN, ne pas ouvrir de port public,
ne pas modifier la politique Cloudflare ni créer de jeton dans ce chantier.
