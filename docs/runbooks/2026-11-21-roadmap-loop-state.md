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

## Bloqués

| Item | Bloqué par | Question ou commande exacte |
| --- | --- | --- |
| F07 / H14 — source des ressources par App | décision du propriétaire | cAdvisor est désactivé par Compose ; quelle source remplace `job="truenas_cadvisor"` pour la heatmap et la topologie : les graphes netdata par App de TrueNAS (`reporting.netdata_get_data`, déjà lus par `home_appliance_pulse`) ou un cAdvisor allégé ? Sans réponse, la heatmap reste vide. Pour lister les graphes disponibles sur TrueNAS : `midclt call reporting.netdata_graphs \| jq -r '.[].name' \| grep -i app` |
| F07 — occupation ZFS par service | décision du propriétaire | Peut-on mapper le dataset `/mnt/cpool/<service>` sur le service du catalogue (convention `AGENTS.md`), ou faut-il un champ explicite `x-nabla` dans Compose ? |
| F14 (1) — jobs `Exited (0)` | runtime TrueNAS | Vérifier qu'un code de sortie non nul devient `crashed` : `midclt call app.query '[["name","=","defectdojo"]]' '{"extra":{"retrieve_resources":true}}' \| jq '.[].active_workloads.container_details[] \| {service_name, state}'`. Si oui, un composant `spec.type: job` en `exited` peut passer à `ok` sans faux vert. |
| F01 — `build_revision` TrueNAS | correctif Compose | `scripts/truenas/update-fastapi-sample.sh` construit localement une ref mobile (`REF=master`) sans exporter `FASTAPI_SAMPLE_BUILD_REVISION`, donc l'argument `BUILD_REVISION` de `compose.yml` est vide. Ajouter `export FASTAPI_SAMPLE_BUILD_REVISION="${target}"` avant `compose build`. |
| F01 — `build_revision` Cloud | décision du propriétaire | FastAPI Cloud ne fournit pas de SHA Git documenté (seulement `FASTAPICLOUD_DEPLOYMENT_ID`) et `scripts/stamp_fastapi_deploy_revision.py` n'est appelé par aucun workflow. Faut-il stamper le SHA dans le commit déployé, ou accepter la corrélation par ID de déploiement ? |
| F11 — parité `catalogRevision` | identifiant | Toutes les routes de parité exigent un jeton (`/sickz` est privée, `/api/homelab-services` est retirée) : fournir un jeton SERVICE en lecture sur la workstation. |
| F04 — `Production Smoke` | identifiant | Créer `PRODUCTION_SMOKE_ACCESS_KEY` sur FastAPI Cloud, puis l'environnement GitHub `production-smoke` (restreint à `master`) et son secret. |
| F08 — durées de démarrage | runtime TrueNAS | `docker logs fastapi-sample 2>&1 \| grep startup_phase` après le prochain redémarrage (Loki ne collecte pas ces journaux). |
