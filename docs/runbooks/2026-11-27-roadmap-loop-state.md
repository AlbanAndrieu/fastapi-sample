# État de la boucle roadmap — 27/11/2026

Skill `nabla-roadmap-loop`, session fastapi-sample, PR [#460](https://github.com/AlbanAndrieu/fastapi-sample/pull/460) (fusionnée), puis [#461](https://github.com/AlbanAndrieu/fastapi-sample/pull/461) (Draft). Détail des items : [roadmap, section du 27/11](../engineering-roadmap.md#2026-11-27--implémentation-de-la-roadmap--retrait-de-federationtruenas-et-tests-js).

## Périmètre

- **fastapi-sample** : écrit par cette session (seul autre écrivain : la passe OpenClaw horaire à HH:12 sur la même branche ; `git fetch` et fusion avant chaque push).
- **nabla-compose**, **nabla-site-alban** : non écrits ici. Plusieurs sessions y travaillent déjà dans les mêmes checkouts (Nexus #454, Coder #453, ntopng, site-alban #340) et les worktrees sont exclus par la règle locale.

## Compteur

| Passe | Fin | Résultat |
| --- | --- | --- |
| 1 | 27/11 ~21:50 UTC | Recette lecture seule TrueNAS et Cloud (1.44.1), faux `fail` TrueNAS corrigé, `/federation/truenas` retiré, tests JS orphelins réalignés |
| 2 | 27/11 ~23:40 UTC | #460 fusionnée (`b3d6b510`) ; smoke direct : clé Cloud et Redis Cloud acceptés, `checks.freebox` perdu par `/healthz` corrigé (`fix/healthz-freebox-check-20261128`) ; TrueNAS pas encore à jour |
| 3 | 28/11 ~00:00 UTC | Sample TrueNAS coupé 1 à 17 min toutes les ~3 h par le recyclage `--max-requests` sous pression IO (Kafka) : retiré du `Dockerfile` ; réconciliation (roadmap F08, skill `local-first-quality` : L3 en clone partagé) ; correctifs dans #461 |

| 4 | 28/11 ~01:30 UTC | Premier chargement Cloud servi depuis Redis ; master-red transmet la clé de smoke (décision owner) ; skills injectables dans l'agent `/run` ; secret du relais généré sur TrueNAS ; mise à jour de Sample TrueNAS en échec (mémoire), relance à 07:20 Paris |

Réconciliation faite à la passe 3 ; prochaine à la passe 6. Les passes 2 à 5 ne valent que si un blocage tombe (fusion de #460, identifiant owner) : sinon elles se limitent à re-tester les blocages ci-dessous.

## Questions parquées (owner)

1. Fusionner #461 (`/healthz` garde `checks.freebox`, plus de recyclage Gunicorn) ; #460 fusionnée le 27/11 à 23:04 UTC.
2. Relais de services (demandé le 28/11) : secret généré dans `.env.secrets` TrueNAS ; mise à jour vers `master` en échec à 02:10 Paris (mémoire saturée), relance programmée à 07:20 Paris (log `/mnt/cpool/var/nabla/ops-logs/sample-update-20261128-relay-retry.log`) ; ensuite seulement, `TRUENAS_SERVICE_STATUS_RELAY_ENABLED=true` et `TRUENAS_FEDERATION_CLOUD_URL=https://fastapi-sample.fastapicloud.dev` dans `.env` TrueNAS puis redéploiement ; côté Cloud, `fastapi cloud login` par l'owner puis `env set` du secret (copié depuis TrueNAS par tube, jamais affiché) et de `TRUENAS_SERVICE_STATUS_RELAY_ENABLED=true`.
3. Smoke authentifié : master-red transmet la seule clé (décision owner du 28/11, dans #461). Reste à restreindre l'environnement `production-smoke` à `master`.
4. Compose : Apps TrueNAS arrêtées et comptées `fail` (3proxy, ConvertX, Stirling PDF, Zabbix, pgAdmin, Bitcoin Core) : les démarrer, ou les étiqueter `albandrieu.com/operational-state: disabled` si l'arrêt est voulu.
5. Compose : convergence Access des applications `fastapi-sample` et `fastapi-sample-api` avant `HOMELAB_OWNER_ACCESS_SSO=true`.
6. Compose : PSI IO de l'hôte à 50–78 % le 27/11 vers 23:30 UTC, latence de lecture `cpool` jusqu'à 0,9 s ; l'App `kafka` lit ~7 Mo/s en continu (chaîne Sentry, runbook : ne pas la réinitialiser). À expliquer côté Compose (rétention, consommateur en boucle ?).
7. Compose : tracearr, paperless-ngx et domain-watchdog passent `--requirepass` en ligne de commande, lisible par `docker inspect` ; ces trois mots de passe Redis ont été affichés dans la session du 28/11 : rotation par l'owner, et mot de passe par fichier ou variable.
8. Agent `POST /run` appelable anonymement sur Cloud (422 sur un corps invalide) : le restreindre à l'owner ou à une clé.

## À re-tester à la passe suivante

- Après déploiement de #460 : la ligne `TrueNAS` de `/api/ui/services` sur TrueNAS n'est plus `fail` (TrueNAS servait encore `02aab185` le 27/11 vers 23:30 UTC, conteneur démarré le 26/11).
- Après déploiement de #461 : plus de `Worker exiting` hors redémarrage du conteneur, RSS stable sur 24 h.
- Cloud : ligne `Plumber API` en `fail` (sonde légère) alors que TrueNAS la voit `warn`.
- F13 : Bitcoin Core `fail` hors fenêtre nocturne au lieu de `scheduled` (étiquette `operational-schedule: night` encore présente ?).
