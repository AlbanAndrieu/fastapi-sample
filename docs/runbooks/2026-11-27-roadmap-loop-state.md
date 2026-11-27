# État de la boucle roadmap — 27/11/2026

Skill `nabla-roadmap-loop`, session fastapi-sample, PR [#460](https://github.com/AlbanAndrieu/fastapi-sample/pull/460) (Draft). Détail des items : [roadmap, section du 27/11](../engineering-roadmap.md#2026-11-27--implémentation-de-la-roadmap--retrait-de-federationtruenas-et-tests-js).

## Périmètre

- **fastapi-sample** : écrit par cette session (seul autre écrivain : la passe OpenClaw horaire à HH:12 sur la même branche ; `git fetch` et fusion avant chaque push).
- **nabla-compose**, **nabla-site-alban** : non écrits ici. Plusieurs sessions y travaillent déjà dans les mêmes checkouts (Nexus #454, Coder #453, ntopng, site-alban #340) et les worktrees sont exclus par la règle locale.

## Compteur

| Passe | Fin | Résultat |
| --- | --- | --- |
| 1 | 27/11 ~21:50 UTC | Recette lecture seule TrueNAS et Cloud (1.44.1), faux `fail` TrueNAS corrigé, `/federation/truenas` retiré, tests JS orphelins réalignés |

Réconciliation prévue à la passe 3. Les passes 2 à 5 ne valent que si un blocage tombe (fusion de #460, identifiant owner) : sinon elles se limitent à re-tester les blocages ci-dessous.

## Questions parquées (owner)

1. Fusionner #460 : seule voie de déploiement des correctifs (la boucle ne fusionne jamais).
2. Activer le relais de services : `TRUENAS_FEDERATION_SECRET` (≥ 32 caractères) sur Cloud et TrueNAS, `TRUENAS_SERVICE_STATUS_RELAY_ENABLED=true` des deux côtés, `TRUENAS_FEDERATION_CLOUD_URL` sur TrueNAS et `REDIS_URL` sur Cloud.
3. `PRODUCTION_SMOKE_ACCESS_KEY` sur FastAPI Cloud et dans l'environnement GitHub `production-smoke`.
4. Compose : Apps TrueNAS arrêtées et comptées `fail` (3proxy, ConvertX, Stirling PDF, Zabbix, pgAdmin, Bitcoin Core) : les démarrer, ou les étiqueter `albandrieu.com/operational-state: disabled` si l'arrêt est voulu.
5. Compose : convergence Access des applications `fastapi-sample` et `fastapi-sample-api` avant `HOMELAB_OWNER_ACCESS_SSO=true`.

## À re-tester à la passe suivante

- Après déploiement de #460 : la ligne `TrueNAS` de `/api/ui/services` sur TrueNAS n'est plus `fail`.
- Cloud : ligne `Plumber API` en `fail` (sonde légère) alors que TrueNAS la voit `warn`.
- F13 : Bitcoin Core `fail` hors fenêtre nocturne au lieu de `scheduled` (étiquette `operational-schedule: night` encore présente ?).
