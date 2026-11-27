# Cloud probe evidence: guide d'exploitation

## Sens des chiffres

`eligible` compte les emplacements publics et les emplacements LAN *activés*.
`known` compte les preuves d'origine ou en mémoire qui ne sont pas périmées.
Les échecs de deadline, preuves périmées et emplacements sans observation ne
sont pas des services déclarés DOWN. `healthy / eligible` n'est pas un SLO.

Le processus limite chaque fenêtre à 12 sondes publiques et 12 LAN, avec
cache de réponse 30 secondes. Les vagues sont déclenchées par des requêtes API,
pas par un daemon de scheduling ; plusieurs workers ont chacun leur propre
mémoire et leur propre rotation. La durée minimale estimée sur **tous** les
candidats est une capacité théorique, pas une promesse de couverture.

## Diagnostic des warnings

- `ACCESS_PROTECTED` : contrôle Cloudflare Access visible, origine non prouvée.
- `AUTH_FAILED` : tentative explicite de jeton de service refusée.
- `ORIGIN_UNVERIFIED` : validation derrière le tunnel insuffisante.
- `DNS`, `TLS`, `TCP`, `TIMEOUT`, `HTTP`, `ORIGIN_ERROR` :
  indice technique de la couche observée ; confirmer avant d'attribuer une panne.
- `DEADLINE`, `STALE`, `NO_EVIDENCE` : qualité de preuve et exécution.

Une réponse HTTP 302/403 de Cloudflare ne doit jamais rendre l'origine verte.
Les données brutes d'une matrice protégée nécessitent l'autorisation OWNER.

## Recette après déploiement

1. Vérifier le SHA et la version effectivement en service.
2. Examiner `/api/homelab/probes` depuis une session autorisée : `probe_summary.public.unobserved_slots`, `estimated_full_cycle_seconds`, `probe_runtime.estimate_source`.
3. Capturer une suite d'observations à intervalle régulier. Si Redis est désactivé, conserver le même worker si possible ; sinon la couverture varie d'un worker à l'autre. Vérifier que chaque ID quitte `unobserved_slots` ou justifier son exclusion.
4. Regrouper chaque warning par `error_kind`, `http_status`, `public_probe_auth_mode` et `public_probe_verification`. Corriger la cause, ne pas modifier artificiellement les états.
5. Si le runtime est répliqué, configurer `REDIS_URL` et activer explicitement `HOMELAB_PUBLIC_PROBE_EVIDENCE_REDIS_ENABLED=true`. Définir `HOMELAB_PROBE_EVIDENCE_NAMESPACE` (identifiant alphanumérique, `_` ou `-`) pour isoler les déploiements. Les seuls champs partagés sont des diagnostics publics nettoyés ; TTL maximal 3600 s. Le backend continue en mémoire si Redis est absent ou inaccessible. Vérifier `probe_summary.public.evidence_storage` et `probe_runtime.evidence_storage`. Aucune donnée LAN n'est fédérée par défaut.
6. Relais TrueNAS → Cloud signé : uniquement `POST /federation/services` (voir [plus bas](#2026-11-26--relais-des-états-lan-signés-code-non-activé)). L'ancien agrégat `POST /federation/truenas` (`truenas_api`/`stage`, `lan_relay` du drill-down) est **retiré le 27/11** : redondant avec ce relais, il partageait ses réglages et aurait réveillé Cloud à chaque sonde TrueNAS. Ne jamais activer les connexions LAN depuis le runtime Cloud.

**Critère d'acceptation :** chaque cible éligible a une observation exploitable
ou une exclusion motivée ; les avertissements Access restent distincts d'une
panne origine ; les délais affichés ne sont pas présentés comme une garantie.


## 2026-11-26 — Etats absents sur l'accueil FastAPI Cloud

- `GET /api/ui/services` est un **répertoire public sans clé**. En mode FastAPI Cloud, `FASTAPI_CLOUD_PUBLIC_DEEP_PROBES_ENABLED=false` (défaut) consulte seulement le snapshot mémoire (`peek_public_health_board_snapshot`) : un nouveau replica sans collecte OWNER répond `boardState=pending` et ses services sont `UNKNOWN`. Ni le Wi-Fi Freebox du navigateur ni `HOMELAB_TRUSTED_CIDRS` ne constituent une preuve de santé ou une identité OWNER. Les endpoints détaillés conservent une authentification explicite et une restriction source selon le déploiement.
- Régression UI identifiée : Python autorise l'état `scheduled` alors que le validateur navigateur le rejetait et pouvait masquer le répertoire entier. Le frontend accepte désormais cet état, l'affiche en bleu neutre (`SCHEDULED`) et l'exclut des échecs. Les compteurs distinguent `UNKNOWN` et `SCHEDULED`, sans synthétiser de `OK`/`FAIL`.
- La fédération HMAC `/federation/truenas` (retirée le 27/11) transmettait exclusivement l'état agrégé API/stage TrueNAS, **pas** la santé par service. Aucun état LAN fiable n'est donc restauré sur Cloud par cette voie. La solution de fond exige un relais **signé et à TTL**, fondé sur les preuves effectivement collectées par TrueNAS, avec stockage partagé Redis côté Cloud, vérification de révision du catalogue, anti-rejeu, limitation des champs publics et état `UNKNOWN` après expiration. Ne jamais activer le fan-out public simplement pour rendre les cartes vertes.
- Vérification après déploiement : visiter `/api/ui/services`, inspecter `boardState`, `catalogSource`, le nombre de `scheduled` puis vérifier la même session sur `/` ; contrôler `/api/ui/session` (`authenticated` seulement si propriétaire authentifié). Sur TrueNAS, vérifier le snapshot OWNER et son horodatage. Les endpoints Cloud ne prouvent **pas** la connectivité LAN.

## 2026-11-26 — Collecte publique légère indépendante du health-board

- Le budget FastAPI Cloud désactive le **deep fan-out**, pas le besoin de statut : `FASTAPI_CLOUD_PUBLIC_LIGHT_PROBES_ENABLED=true` par défaut, `false` comme arrêt d'urgence. Aucune clé OWNER dans le navigateur. La route anonyme `/api/ui/services` lance au plus **neuf requêtes HEAD toutes les 180 s par worker actif**, avec trois connexions simultanées, délai HTTP 2 s, budget de vague 5 s, et horloge de fraîcheur individuelle de 15 min. La première réponse peut rester `pending`, puis devient `fresh` lorsqu'au moins une observation publique vérifiée existe.
- Cibles uniquement issues des routes HTTPS publiques validées par Backstage V2, domaines Nabla autorisés, jamais les destinations `*.int`, LAN, honeypots, endpoints non-HTTPS, ports atypiques, ou valeurs de requête. Préflight DNS global obligatoire, pas de redirection ni proxy d'environnement, aucun contenu HTTP lu dans les corps GET de secours. Aucun sondage Prometheus/Cloudflare/TrueNAS.
- Routes protégées par Access : sondées uniquement si `CF_ACCESS_CLIENT_ID`/`CF_ACCESS_CLIENT_SECRET` (jeton de service `fastapi-sample-monitor`, politique Access réutilisable attachée à 32 applications dans `nabla-compose/terraform/cloudflare`) sont configurés, et uniquement vers `albandrieu.com`/`*.albandrieu.com`. Le jeton n'accompagne que la requête HEAD (ou GET de secours) de la route, jamais une redirection. 2xx = route joignable de bout en bout (edge, tunnel, origine) ; redirection Access ou 401/403 = jeton refusé par la politique de l'application, `unknown` ; 5xx/530 = échec observé côté public, pas un verdict interne. Le snapshot catalogue donne 25 cibles avec jeton (23 protégées) contre 2 sans.
- `2xx` signifie **HTTP public OK** (pas un verdict de santé applicative), `4xx` hors autorisation et `5xx` donnent `FAIL` de l'endpoint public seulement ; `3xx`, `401`, `403`, `429`, timeouts ou DNS non validé restent `UNKNOWN`. Les services exclusivement LAN restent `UNKNOWN` tant qu'une vraie preuve LAN signée n'est pas disponible.
- Le résultat n'est pas un cache durable multi-réplicas ; les échantillons expirent et les cold starts repartent `UNKNOWN`. Étape future : reporter les preuves LAN minimisées avec signatures HMAC, anti-rejeu, révision catalogue et stockage partagé. Ne pas fabriquer un `OK` à partir du seul catalogue.

## 2026-11-26 — Relais des états LAN signés (code non activé)

Le service TrueNAS publie vers `POST /federation/services` sur FastAPI Cloud les verdicts de **sa propre vue publique** `/api/ui/services` (déjà servie en anonyme sur TrueNAS : noms et états résumés), lue en interne (ASGI, sans réseau ni port) et convertie en nom d'entité Backstage ; titres ambigus et `unknown` exclus, tableau `fresh` Backstage v2 de la même révision exigé. Mesure du 26/11 (21:10 UTC, TrueNAS `v0+1.44.0`) : 119 états confirmés sur 217 relayés (82 ok, 24 warn, 6 fail, 7 scheduled), corps signé de 5,3 Ko ; l'ancienne projection des seules sondes directes n'en portait que 24. Contrat strict : `catalogRevision`, horodatages UTC, expiration 12 h 30, nonce, et au plus 300 couples `id/state/age` (corps ≤ 32 Kio). Un relevé expiré, non observé, sans âge fiable ou sans signature HMAC est refusé. Les IP, hôtes, ports, URL, diagnostics, secrets et détails de sécurité ne traversent pas le relais. Authentification HMAC avec séparation de domaine, rejeu et ordre des écritures contrôlés par Redis si présent. L'UI publique ne joint un statut qu'à un service connu du catalogue révisionnel, jamais à un identifiant issu librement de la requête.

**Activation explicite** après recette : `TRUENAS_SERVICE_STATUS_RELAY_ENABLED=true` des deux côtés, la même clé `TRUENAS_FEDERATION_SECRET` (au moins 32 caractères, coffre), `TRUENAS_FEDERATION_CLOUD_URL=https://fastapi-sample.fastapicloud.dev` sur TrueNAS et `REDIS_URL` sur Cloud, **obligatoire** : sans Redis, les états reçus restent en mémoire du réplica et disparaissent à chaque mise en veille (scale-to-zero), si bien qu'un créneau de réveil ne sert qu'aux visites faites avant la mise en veille suivante ; ils ne sont pas non plus partagés entre réplicas. Aucun cron système : l'horloge est une tâche de fond de l'application TrueNAS, démarrée seulement si le producteur est actif. Créneaux de réveil choisis par l'owner : **08:00, 12:00, 18:00 et 21:00, heure de Paris** ; à chaque créneau, TrueNAS lit sa vue publique (jusqu'à 4 lectures espacées de 30 s, le tableau santé se rafraîchissant en arrière-plan), l'envoie, et réessaie une fois 5 min plus tard en cas d'échec. Aucun envoi entre deux créneaux (une seule source, pas d'écrasement par des sondes partielles). Gatus ne sonde que `/health` et ne rafraîchit donc pas le tableau. Délai HTTP de 30 s pour absorber le démarrage à froid du Cloud ; au moins 5 min entre deux envois et au plus 24 par jour glissant et par worker, en filet de sécurité. Chaque POST réveille FastAPI Cloud (Hobby : 180 heures-réplicas Nano, scale-to-zero) : le coût du relais est de 4 réveils programmés par jour (8 au pire avec les nouvelles tentatives). Le Cloud reste en veille entre les créneaux (minimum de réplicas forcé à 0 sur Hobby) ; la sonde légère Cloud ne tourne que pendant les visites. Un relevé relayé de plus de 15 min est affiché `boardState=stale` (historique), jamais `fresh`. La vue `/api` affiche alors les derniers états en gris (« LAST OK », plus de 15 min), jamais comme verdict actuel ni comme `unknown` ; l'accueil `/` ne compte que les états vérifiés. L'expiration couvre le plus long silence entre créneaux (21:00 → 08:00, 12 h la nuit du passage à l'heure d'hiver) plus 30 min. Déployer Cloud avant TrueNAS : un Cloud antérieur refuse l'expiration de 12 h 30 (422). La configuration ne peut pas être déclarée active sans contrôle des véritables émissions 202 et des lectures, avec `boardState` et version du catalogue concordants.

**À qualifier avant activation :** statuts HTTP publics et TCP internes ont des sémantiques différentes (TCP ouvert n'implique pas service applicatif sain), limites du TTL et de la rotation des sondes, gestion des sources Access, politique d'accès réseau du nouveau routeur Freebox, contrôle du coût Cloud et absence de publication accidentelle de valeurs internes.

**Sécurité de réception :** le flux JSON est lu en streaming avec un plafond 16 Kio avant vérification HMAC ; les corps surdimensionnés ne sont jamais conservés intégralement en mémoire. Un refus de Redis n'autorise pas un repli silencieux en écriture mémoire multi-réplicas. Toute réponse publique garde ses propres règles de minimisation et d'authentification.

**Sémantique des états du relais :** HTTP 2xx authentifié jusqu'à l'origine ou 2xx public réellement observé peut confirmer `OK` de l'endpoint. Un simple HTTP 302, challenge Access ou TCP ouvert ne prouve pas l'application : ces signaux ne deviennent pas un faux `OK`. Un TCP LAN ouvert est affiché `WARN` (connectivité uniquement). Les échecs observés restent attribués au point de vue de la sonde.
