# Boucle roadmap — état et questions en attente (21/11/2026)

Mode sprint homelab approuvé par le propriétaire le 21/11/2026. PR unique du
dépôt : [#452](https://github.com/AlbanAndrieu/fastapi-sample/pull/452).
Périmètre : [roadmap FastAPI](../engineering-roadmap.md) et lignes du
portefeuille détenues par FastAPI (H06, H14, parties FastAPI de H05, H11,
H13, H16, H17, H20, H21). Ce dépôt ne déploie ni sur TrueNAS ni sur FastAPI
Cloud dans cette boucle : un autre agent possède ces runtimes.

## Compteur

| Passe | Date | Vantage | Résultat |
| --- | --- | --- | --- |
| 1 | 21/11 | workstation, sondes HTTP en lecture seule | inventaire H14, corrections de la roadmap, questions ci-dessous |
| 2 | 21/11 | workstation, sondes HTTP en lecture seule | jauge F08, `composeProfiles`/`on_demand`, réconciliation F01 et Compose |

Prochaine réconciliation complète (roadmaps, skills, docs, refactor) : passe 3.

## Observations de la passe 1 (lecture seule, 21/11 vers 00:20 UTC)

- `/v2/version` anonyme : Cloud `1.39.0`, TrueNAS (`172.17.0.24:8091`)
  `1.38.2`, `build_revision` à `null` des deux côtés. TrueNAS a donc une
  release de retard sur `master`.
- `/sickz`, `/api/homelab/status`, `/api/homelab/health` et
  `/api/site/catalog/v2` répondent 401 en anonyme sur Cloud et TrueNAS :
  `DENIED`, jamais `DOWN`.
- Loki ne reçoit que les jobs `pfsense` et `suricata` : les journaux
  `startup_phase` de F08 n'y sont pas.
- Prometheus : aucune série cAdvisor, flux pfSense vides ; détail dans
  [l'inventaire H14](dashboard-coverage-inventory.md).

## Observations de la passe 2 (lecture seule, 21/11 vers 01:52 UTC)

- `/v2/version` anonyme : Cloud `1.39.0`, TrueNAS `8091` toujours `1.38.2`, `build_revision` à `null` des deux côtés.
- Prometheus : `up{job="fastapi_sample"}` = 1 sur `172.17.0.24:8091`, métriques applicatives présentes ; la jauge de démarrage F08 y sera lisible après déploiement.
- nabla-compose : #430 (Draft) porte la garde publique du cron et `c7ce1981` (`build_revision`) ; les doublons H04/H05 du portefeuille sont fusionnés sur `master`. Les endpoints observateur TrueNAS répondent 401 sans `X-Diagnostics-Key` ; le lecteur côté hôte annoncé par Compose n'est pas encore publié (01:55 UTC).
- Aucune nouvelle question owner.

## Bloqués

| Item | Bloqué par | Question ou commande exacte |
| --- | --- | --- |
| F07 / H14 — source des ressources par App | décision du propriétaire | cAdvisor est désactivé par Compose ; quelle source remplace `job="truenas_cadvisor"` pour la heatmap et la topologie : les graphes netdata par App de TrueNAS (`reporting.netdata_get_data`, déjà lus par `home_appliance_pulse`) ou un cAdvisor allégé ? Sans réponse, la heatmap reste vide. Pour lister les graphes disponibles sur TrueNAS : `midclt call reporting.netdata_graphs \| jq -r '.[].name' \| grep -i app` |
| F07 — occupation ZFS par service | décision du propriétaire | Peut-on mapper le dataset `/mnt/cpool/<service>` sur le service du catalogue (convention `AGENTS.md`), ou faut-il un champ explicite `x-nabla` dans Compose ? |
| F14 (1) — jobs `Exited (0)` | runtime TrueNAS | Vérifier qu'un code de sortie non nul devient `crashed` : `midclt call app.query '[["name","=","defectdojo"]]' '{"extra":{"retrieve_resources":true}}' \| jq '.[].active_workloads.container_details[] \| {service_name, state}'`. Si oui, un composant `spec.type: job` en `exited` peut passer à `ok` sans faux vert. |
| F01 — `build_revision` TrueNAS | fusion Compose | Correctif `c7ce1981` sur la branche de nabla-compose#430 (Draft) : il exporte `FASTAPI_SAMPLE_BUILD_REVISION` avant `compose build`. Après fusion et mise à jour : `curl -s http://172.17.0.24:8091/v2/version \| jq .build_revision` doit rendre le SHA déployé. |
| F01 — `build_revision` Cloud | décision du propriétaire | FastAPI Cloud ne fournit pas de SHA Git documenté (seulement `FASTAPICLOUD_DEPLOYMENT_ID`) et `scripts/stamp_fastapi_deploy_revision.py` n'est appelé par aucun workflow. Faut-il stamper le SHA dans le commit déployé, ou accepter la corrélation par ID de déploiement ? |
| F11 — parité `catalogRevision` | identifiant (V1 : Vaultwarden verrouillé) | Toutes les routes de parité exigent un jeton (`/sickz` est privée, `/api/homelab-services` est retirée) : fournir un jeton SERVICE en lecture sur la workstation. |
| F04 — `Production Smoke` | identifiant (V1 : Vaultwarden verrouillé) | Créer `PRODUCTION_SMOKE_ACCESS_KEY` sur FastAPI Cloud, puis l'environnement GitHub `production-smoke` (restreint à `master`) et son secret. |
| F08 — durées de démarrage | déploiement TrueNAS | Après démarrage d'un SHA contenant `ded6e023` : `max by (phase) (nabla_startup_phase_duration_seconds{job="fastapi_sample"})` dans Prometheus, sans `docker logs`. |
