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

## 5. Validation avant clôture

Vérifier séparément (a) les 89 tests de contrat déjà exécutés sur
l'ancien HEAD, (b) les nouveaux tests du dernier HEAD FastAPI,
(c) les deux jobs Akvorado côté Prometheus LAN, et (d) le DTO Cloud.
Les tests passés sur un ancien SHA ne sont pas réutilisés comme preuve.
Le diagnostic doit rester lecture seule ; ne pas générer
une relance forcée de sondes.
