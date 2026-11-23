# Boucle roadmap — état et questions en attente (21/11/2026)

Mode sprint homelab approuvé par le propriétaire le 21/11/2026. PR de la passe 1
et 2 : [#452](https://github.com/AlbanAndrieu/fastapi-sample/pull/452), fusionnée le 21/11 à 11:58 UTC
(`f21a9b75`) ; la suite est sur la branche `fix/roadmap-pass2-followup-20261121`.
Périmètre : [roadmap FastAPI](../engineering-roadmap.md) et lignes du
portefeuille détenues par FastAPI (H06, H14, parties FastAPI de H05, H11,
H13, H16, H17, H20, H21). Ce dépôt ne déploie ni sur TrueNAS ni sur FastAPI
Cloud dans cette boucle : un autre agent possède ces runtimes.

## Compteur

| Passe | Date | Vantage | Résultat |
| --- | --- | --- | --- |
| 1 | 21/11 | workstation, sondes HTTP en lecture seule | inventaire H14, corrections de la roadmap, questions ci-dessous |
| 2 | 21/11 | workstation, sondes HTTP en lecture seule | jauge F08, `composeProfiles`/`on_demand`, réconciliation F01 et Compose ; puis F14 (1), F01 Cloud, F07 ZFS et décisions owner |

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

## Décisions owner du 21/11

- F07 source par App : graphes netdata TrueNAS par App, sans cAdvisor. Non implémentable telle quelle (aucun graphe par App dans TrueNAS 27.0.0-RC.1) : question corrigée ci-dessous.
- F07 occupation ZFS : convention `/mnt/cpool/<service>`, `x-nabla` seulement en dérogation : **CODED/TESTED** (`185459dd`).
- F01 Cloud : corrélation par `FASTAPICLOUD_DEPLOYMENT_ID`, sans stamp du SHA : **CODED/TESTED** (`a8bc02df`).
- O1 (F18) : canal Slack OpenClaw en sortie seule, identité existante, canal fixe : consignée, non codée.
- F14 (1), avec la preuve runtime du 21/11 (11:50 UTC) : **CODED/TESTED** (`0da00c38`).

## Bloqués

| Item | Bloqué par | Question ou commande exacte |
| --- | --- | --- |
| F07 / H14 — source des ressources par App | décision owner à corriger | Décision du 21/11 : graphes netdata par App. TrueNAS 27.0.0-RC.1 n'en a pas (`reporting.netdata_get_data` ne sert que `GRAPH_PLUGINS` : CPU, mémoire, disques, interfaces, charge, ARC, UPS) ; sa source par App est l'event source `app.stats` (abonnement, rôle `APPS_READ`, une ligne par App : CPU %, mémoire, réseau rx/tx, blkio). Question : remplacer cAdvisor par `app.stats`, la heatmap et la topologie passant à la granularité App ? Ancien énoncé : cAdvisor est désactivé par Compose ; quelle source remplace `job="truenas_cadvisor"` pour la heatmap et la topologie : les graphes netdata par App de TrueNAS (`reporting.netdata_get_data`, déjà lus par `home_appliance_pulse`) ou un cAdvisor allégé ? Sans réponse, la heatmap reste vide. Pour lister les graphes disponibles sur TrueNAS : `midclt call reporting.netdata_graphs \| jq -r '.[].name' \| grep -i app` |
| F01 — `build_revision` TrueNAS | mise à jour TrueNAS (owner Compose) | Correctif `c7ce1981` (export de `FASTAPI_SAMPLE_BUILD_REVISION` avant `compose build`) fusionné avec nabla-compose#430 le 21/11 (`5b34ef8f`). Après mise à jour : `curl -s http://172.17.0.24:8091/v2/version \| jq .build_revision` doit rendre le SHA déployé. |
| F11 — parité `catalogRevision` | identifiant (V1 : Vaultwarden verrouillé) | Toutes les routes de parité exigent un jeton (`/sickz` est privée, `/api/homelab-services` est retirée) : fournir un jeton SERVICE en lecture sur la workstation. |
| F04 — `Production Smoke` | identifiant (V1 : Vaultwarden verrouillé) | Créer `PRODUCTION_SMOKE_ACCESS_KEY` sur FastAPI Cloud, puis l'environnement GitHub `production-smoke` (restreint à `master`) et son secret. Toujours absent au run `master` du 22/11 (18:29 UTC) ; l'étape Playwright du même run échoue aussi (owner fastapi-sample). |
| F08 — durées de démarrage | déploiement TrueNAS | Après démarrage d'un SHA contenant `ded6e023` : `max by (phase) (nabla_startup_phase_duration_seconds{job="fastapi_sample"})` dans Prometheus, sans `docker logs`. |
