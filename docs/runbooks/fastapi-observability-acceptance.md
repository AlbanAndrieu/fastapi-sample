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

