# FastAPI — diagnostic télémétrie et accès Cloud

**Runbook canonique (25 octobre 2026).**
Le contenu détaillé antérieur reste archivé :
[comparaison Prometheus/Akvorado](../archive/2026-10-24/prometheus-akvorado-health-board.md)
et [incident 403](../archive/2026-10-24/fastapi-cloud-owner-access-403.md).
Ce document ne traite pas du déploiement TrueNAS, de pfSense ou des
secrets source : ils appartiennent à `nabla-compose`.

## Frontières et états

| Plan | Preuve | Ce qu'elle ne prouve pas |
| --- | --- | --- |
| Prometheus LAN | `up{job="akvorado_inlet"}` et outlet | Arrivée de NetFlow ou écriture ClickHouse |
| FastAPI staging | `GET /metrics` via un jeton dédié | Accès anonyme ni santé de la base |
| FastAPI Cloud | `/api/health-board` et `platform_metrics` | Sondes LAN exécutées depuis le cloud |
| Vue `/api` | Cartes et données du DTO | Exactitude sans horodatage/provenance |

Une réponse HTTP 401 est un refus de credentials et une 403 un refus
de politique/identité/source. Elles ne démontrent ni un service DOWN
ni un scrape Akvorado DOWN. Cloudflare Access HTTP 302/403 peut
correspondre à une passerelle accessible dont l'origine est inconnue.

## 1. Diagnostics LAN — depuis un poste autorisé

```bash
# Dans le dépôt fastapi-sample, version contenant le vérificateur :
python3 scripts/verify-prometheus-cloud-projection.py --check --scope lan
```

Le mode LAN lit uniquement `172.17.0.24:9090`, affiche le verdict
Inlet/Outlet et indique explicitement `cloud_projection=NOT_CHECKED`.
Il ne doit **jamais** annoncer une projection cloud validée.

La vue détaillée des targets et métriques fonctionnelles relève du
script Compose `scripts/prometheus/audit-telemetry-coverage.py`.

## 2. Comparaison LAN → FastAPI Cloud

```bash
python3 scripts/verify-prometheus-cloud-projection.py --check --scope both
```

La requête cloud est une lecture avec limite de taille et timeout ;
les redirections externes ne sont pas suivies. La clé diagnostics
peut être lue depuis `DIAGNOSTICS_ACCESS_KEY` (variable en mémoire).
Ne pas fournir sa valeur en argument ni l'afficher.

Résultats :
- `scrape_projected_up` : le job est présent des deux côtés en UP.
- `cloud_metric_not_observed` : la donnée est absente du DTO.
- `lan_cloud_mismatch` : les valeurs diffèrent ; vérifier les SHA,
  provenance, fraîcheur et transformations.
- `CLOUD HTTP 401/403` : autorisation refusée ; **comparaison NOT_RUN**,
  pas verdict DOWN. Ne pas affaiblir le contrôle d'accès.

## 3. Diagnostic 403 — préserver la sécurité

Depuis un hôte autorisé, afficher uniquement le code et les en-têtes
de réponse **non sensibles** :

```bash
curl -sS -D - -o /dev/null --max-time 10 \
  https://fastapi-sample.fastapicloud.dev/api/health-board |
  grep -Ei '^(HTTP/|server:|cf-ray:|cf-mitigated:|www-authenticate:|location:)'
```

Vérifier dans l'ordre : SHA déployé, politique Cloudflare Access,
présence d'une session propriétaire, clé diagnostics et plage IP
source effectivement attestée par le proxy ASGI. Un
`HOMELAB_TRUSTED_CIDRS` client n'est pas un
`HOMELAB_TRUSTED_PROXY_CIDRS`. Les en-têtes
`X-Forwarded-For` non fiables ne doivent pas être acceptés.
Ne pas configurer `0.0.0.0/0` comme proxy de confiance,
ne pas afficher `Authorization` ou `Set-Cookie`.

## 4. Authentification du scrape staging

La [PR FastAPI #376](https://github.com/AlbanAndrieu/fastapi-sample/pull/376)
introduit `METRICS_SCRAPE_KEY` limité à `GET/HEAD /metrics`.
Cela ne résout **pas** le 403 cloud, lequel concerne une route différente.
La clé de métriques ne donne pas accès aux API diagnostiques.
Déployer le code et le secret avant que Compose puisse utiliser un
`authorization.credentials_file` en lecture seule.
Ne pas rendre `/metrics` public ni partager
`DIAGNOSTICS_ACCESS_KEY` avec Prometheus.


## 6. Gatus — comparer la configuration aux métriques sans réseau

Effectuer ce contrôle sur une workstation autorisée, avec une copie **locale**
de `nabla-compose/apps/gatus/config/config.yml`. FastAPI n'interroge
aucun service lors de l'ouverture d'une carte.

1. Afficher les 85 monitors actuellement déclarés dans la configuration
   (63 TCP, 21 HTTP, 1 HTTPS à la date du 25 octobre 2026). Ce chiffre décrit
   le fichier Git, pas la disponibilité de l'installation TrueNAS :

   ```sh
   just gatus-inventory ../nabla-compose/apps/gatus/config/config.yml
   ```

2. Exporter séparément le JSON autorisé de `/api/health-board` dans un
   fichier privé hors du dépôt. Ne pas committer les diagnostics, clés ou
   adresses privées.

3. Rapprocher les déclarations et échantillons :

   ```sh
   just gatus-compare ../nabla-compose/apps/gatus/config/config.yml /chemin/prive/health-board.json
   ```

4. Lire les classes `up`, `down`, `no_sample`, `unverified`, les
   labels ambigus et les séries observées sans déclaration. Le code retour
   `1` signifie **contrôle incomplet ou anomalie**, jamais nécessairement
   panne du service. Le script sort `2` si les fichiers sont invalides.

5. Sur les échecs réels, comparer la cible de la définition Gatus, le
   statut HTTP/TCP/TLS, l'authentification, puis les règles Prometheus.
   Les mesures enregistrées par `max by (nabla_service_id, type)`
   peuvent masquer une panne si deux monitors partagent ces labels.
   Une telle collision est donc classée `unverified`, jamais `up`.

La preuve est périmée après 180 secondes, ou si le snapshot est incomplet.
Les sondes TCP indiquent seulement une connexion, pas un succès HTTP ni
une disponibilité métier. L'analyse ne lance aucune requête vers les cibles.
Pour les contrats hors ligne : `just gatus-contracts`.

## 5. Validation avant clôture

Vérifier séparément (a) les 89 tests de contrat déjà exécutés sur
l'ancien HEAD, (b) les nouveaux tests du dernier HEAD FastAPI,
(c) les deux jobs Akvorado côté Prometheus LAN, et (d) le DTO Cloud.
Les tests passés sur un ancien SHA ne sont pas réutilisés comme preuve.
Le diagnostic doit rester lecture seule ; ne pas générer
une relance forcée de sondes.

## Réponses d'authentification attendues : Garage et LiteLLM

Le HTTP 403 anonyme sur `http://172.17.0.24:3900/` (Garage S3) et le
HTTP 401 sur `http://172.17.0.24:4000/health` (LiteLLM) ont été
fournis par l'opérateur. Ils prouvent que la couche HTTP a répondu et
appliqué un contrôle d'authentification. Ils ne prouvent ni une opération
S3 signée, ni une inférence LLM, ni une API accessible depuis Internet.

L'interface peut afficher **bleu / Authentification requise (attendu)**,
uniquement pour ces surfaces explicitement reconnues et une observation
anonyme fraîche, sans credentials présentés. Si une clé transmise est
refusée, si le code est inattendu, ou si le TCP/TLS échoue, conserver
l'anomalie. Le vert exige une autre preuve de santé du service.
Le vrai `GET /health/liveliness` de LiteLLM est également interrogé
par son healthcheck Docker Compose. Gatus utilise déjà des vérifications
TCP pour LiteLLM et Garage ; elles n'attestent que la connectivité.

Le verdict **Policy Failed** est distinct : `external=false` ne
signifie pas automatiquement une violation. Une exposition WAN non
autorisée est une violation même lorsqu'elle exige une authentification.
Inversement, une réponse HTTP LAN 403 ne prouve pas un ingress WAN.
L'UI conserve le verdict `/sickz` et ne le convertit jamais en bleu
parce que la route HTTP a refusé un visiteur anonyme.

Script opérateur sans clé : `nabla-compose/scripts/truenas/diagnose-protected-service-http.py`
([Compose #281](https://github.com/AlbanAndrieu/nabla-compose/pull/281)).
Les mesures Docker et Gatus doivent venir du collecteur LAN autorisé,
et non d'un navigateur cloud. Les détails et logs sensibles restent privés.


## 7. Préflight FastAPI /metrics (octobre 2026)

Preuve opérateur : `fastapi_sample` retourne **HTTP 401** au scrape Prometheus. Le code `METRICS_SCRAPE_KEY` a été fusionné en #376 ; cela ne prouve pas que la clé est correctement installée dans les deux processus.

Depuis **TrueNAS** en lecture seule :

```bash
python3 scripts/truenas/diagnose-fastapi-metrics-auth.py --check
```

Un `401` anonyme est un **contrôle d'accès actif**, pas une panne FastAPI. Sans secret local, le résultat `key_configured_scraper_credentials_unverified` est **UNVERIFIED**, non `PASS`. Avec un fichier de clé privée détenu par l'opérateur (chemin hors Git, permission `0600` ou `0640`, jamais lisible par tout le monde), contrôler explicitement le même jeton :

```bash
sudo python3 scripts/truenas/diagnose-fastapi-metrics-auth.py --check \
  --token-file /chemin/prive/metrics-scrape-token
```

L'outil imprime **uniquement** les statuts HTTP et des catégories prédéfinies. Un `401` authentifié indique une clé rejetée ; `200` authentifié prouve uniquement l'autorisation de `/metrics`, pas la réussite du scrape Prometheus. `503` anonyme indique une gate ou une configuration de clé indisponible. Ne jamais copier le secret dans une commande `curl -v`, dans Git, ni dans un commentaire PR.

La correction éventuelle du fichier `authorization.credentials_file`, des montages Prometheus ou des secrets TrueNAS appartient à `nabla-compose`. **Ne pas désactiver** `METRICS_SCRAPE_KEY`, `OPS_ROUTE_POLICY_STRICT` ou la politique d'accès pour forcer `up=1`.

### Diagnostic distant depuis la workstation via SSH

Cette option envoie **uniquement le code du diagnostic** sur l'entrée
standard de Python à TrueNAS. Aucun secret local n'est transmis.
L'hôte est fixé à `172.17.0.24`. SSH exige une clé d'hôte déjà connue
(`StrictHostKeyChecking=yes`) et refuse l'authentification interactive.

Depuis un poste disposant d'un accès SSH autorisé à TrueNAS :

```bash
python3 scripts/truenas/diagnose-fastapi-metrics-auth.py --check \
  --ssh-target albandrieu@172.17.0.24
```

Remplacer `albandrieu` par le compte SSH **déjà autorisé** si nécessaire.
L'outil ne crée aucun compte, n'installe aucun service et ne publie pas
le port 8091.

Si la commande renvoie `ssh_unavailable_or_report_invalid`,
mettre à jour le worktree avec la dernière version de #378.
Le diagnostic signale désormais des causes **bornées** :
`ssh_host_key_untrusted`, `ssh_authentication_denied`,
`ssh_connection_refused`, `ssh_connection_timeout`,
`ssh_network_unreachable`, `ssh_session_rejected`,
`remote_python_unavailable`, `remote_report_invalid` ou
`ssh_client_options_invalid`. La sortie `next_check` contient
une procédure statique ; aucun message SSH libre n'est publié.

Pour confirmer la connexion SSH et la présence de Python avant
de tester `/metrics`, lancer séparément sur la workstation :

```bash
ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o ConnectTimeout=7 albandrieu@172.17.0.24 \
  'command -v python3 >/dev/null' >/dev/null 2>/dev/null \
  && echo SSH_PYTHON_OK || echo SSH_PYTHON_NOT_VERIFIED
```

Cette commande ne lit aucune clé de métriques. Ne pas désactiver
`StrictHostKeyChecking`.

**Retour opérateur du 26 octobre 2026 :** la commande SSH ci-dessus
(sans `-p`) affiche `SSH_PYTHON_OK`, tandis que la version précédente
du script (avec `-p 22` imposé) annonçait
`ssh_connection_refused`. L'hypothèse principale est un port SSH
personnalisé dans la configuration locale, non une panne SSH TrueNAS.
Depuis la version corrigée de #378, `--ssh-target` n'ajoute plus
`-p 22` par défaut. `--ssh-port N` reste possible si un remplacement
est explicitement demandé.

Pour afficher **uniquement le port effectif** utilisé par OpenSSH
sans copier les autres paramètres du client :

```bash
ssh -G albandrieu@172.17.0.24 |
  awk '$1 == "port" { print "SSH_CONFIG_PORT=" $2; exit }'
```

Ne pas afficher `ssh -G` complet dans les tickets : les chemins
IdentityFile et ProxyCommand peuvent contenir des informations locales.
 Si la clé d'hôte est inconnue ou a changé,
contrôler son empreinte depuis la console TrueNAS avant de l'approuver.
En cas de refus d'authentification, vérifier le compte SSH,
sa clé publique autorisée et son shell. Un compte API TrueNAS n'a
pas nécessairement accès à SSH. Le script ne modifie aucune configuration.

**Important :** `/chemin/prive/metrics-scrape-token` est un exemple
de chemin. Ne pas l'utiliser tel quel et ne pas créer de secret
de remplacement avant de réconcilier le jeton réellement utilisé
par Prometheus.

Pour tester avec un secret existant sur TrueNAS, indiquer son **chemin
distant absolu**, sans transmettre la valeur depuis la workstation :

```bash
python3 scripts/truenas/diagnose-fastapi-metrics-auth.py --check \
  --ssh-target albandrieu@172.17.0.24 \
  --token-file /chemin/prive/metrics-scrape-token
```

Le fichier distant doit être un fichier régulier non symbolique,
lisible par le compte SSH et non lisible par tout le monde (`0600` ou
`0640`). Le résultat `scrape_auth_accepted` prouve l'accès local
à `/metrics`, mais **pas** que le processus Prometheus utilise ce
même secret dans `authorization.credentials_file`. Une erreur SSH produit une catégorie de transport ou de rapport distant,
jamais une conclusion de panne FastAPI.
Ce mode exige un accès réseau LAN/VPN déjà existant ; aucun tunnel
Cloudflare ou ouverture WAN n'est créé.

### Collecte Prometheus FastAPI — preuve du 26 octobre 2026

L'opérateur a confirmé depuis la workstation :
- `ssh -G albandrieu@172.17.0.24` : port effectif **9922**.
- Diagnostic avec `--ssh-target` corrigé : `origin=truenas_ssh`,
  `anonymous_http=401`, `credentials_tested=false`,
  `key_configured_scraper_credentials_unverified`.
- Le port SSH personnalisé explique le `ssh_connection_refused` antérieur
  lorsque le script imposait le port 22. La connexion distante fonctionne.

**Responsabilité inter-dépôts :** l'accès anonyme HTTP 401 prouve que
`/metrics` répond et exige une identité machine. Il ne valide pas le
scrape. Le code FastAPI accepte la clé `METRICS_SCRAPE_KEY` via
`Authorization: Bearer` et `X-Metrics-Key`. Dans le dépôt Compose,
`apps/prometheus/prometheus.yml` déclare `job_name: fastapi_sample`
avec la cible `172.17.0.24:8091`, **mais ne déclare pas encore**
`authorization` ni `credentials_file` pour ce job sur la branche
vérifiée (26/10/2026). Cela explique le HTTP 401 si la configuration
déployée est identique. La configuration effective et les secrets restent
à vérifier avant de corriger Compose.

Séquence de correction, sans sortie de secret :

1. Vérifier le job `fastapi_sample` dans la configuration active
   de Prometheus sur TrueNAS. Ne pas afficher sa réponse brute.
2. Provisionner un **jeton dédié** et identique côté runtime FastAPI
   et côté fichier de credentials Prometheus, via la gestion de secrets
   existante. Ne pas créer le fichier dans Git.
3. Déclarer `authorization.type: Bearer` et
   `authorization.credentials_file` sous le seul job
   `fastapi_sample` dans `nabla-compose`.
4. Tester en local `promtool check config`, les permissions du secret
   pour l'UID `568` et le montage Compose avant tout déploiement.
5. Faire valider le déploiement puis vérifier
   `up{job="fastapi_sample"} == 1`. Ce signal prouve le scrape,
   non la disponibilité fonctionnelle de l'application.

Ne pas utiliser `DIAGNOSTICS_ACCESS_KEY` pour Prometheus, ne pas
désactiver l'authentification, et ne pas divulguer d'empreinte de clé.
Le diagnostic FastAPI affiche désormais `next_check` avec un code fixe,
sans refléter les commandes ni les valeurs reçues depuis SSH.

Les routes machine `/api/site/health/v2` et `/api/site/catalog/v2` exigent toujours une clé diagnostics valide même lorsque `HOMELAB_PUBLIC_DIAGNOSTICS_READONLY=true`. L'accusé de trace n'est jamais fourni aux requêtes refusées.
