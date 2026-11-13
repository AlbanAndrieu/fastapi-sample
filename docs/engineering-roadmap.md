# Roadmap d’ingénierie — FastAPI Sample

**Réconciliée le 13 novembre 2026.** Une tâche ci-dessous représente un **résultat à réceptionner** et non une PR à créer. Les observations datées, checklists historiques et descriptions des anciens correctifs sont conservées dans l’[archive du 13 novembre](archive/2026-11-13/engineering-roadmap-before-reconciliation.md).

**Statuts :** CODED (présent dans Git), TESTED (vérifié au SHA exact), DEPLOYED (révision déployée identifiée), ACCEPTED (fonctionnement constaté sur l’environnement cible). Un merge, un 401/403 d’accès, un NOT_RUN ou une preuve obsolète ne sont pas une réception.

## Décisions de priorité à arbitrer

| Choix | Groupe | Résultat attendu | Dépendance |
| --- | --- | --- | --- |
| **F1 — P0 (recommandé)** | E01–E04 | Stable en production, budget Cloud mesuré, qualité et identité de build | Accès navigateur / panneau FastAPI Cloud |
| **F2 — P0/P1** | E05–E08 | Sondes crédibles et parcours OWNER sur TrueNAS + Cloud | Compose, collecte LAN |
| **F3 — P1/P2** | E09–E14 | UX enrichie, dette maîtrisée et fonctionnalités avancées | A et B acceptés |

Le choix F1–F3 porte sur l’**ordre des travaux FastAPI**. Pour arbitrer entre tous les dépôts, utiliser la [vue générale G1–G7 de Compose](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap.md). Aucune validation de production n’a été effectuée dans cette réconciliation documentaire.

## P0 — Publication, coût et contrôles

| ID | Action à réceptionner | État documenté et preuve de fin |
| --- | --- | --- |
| **E01** | **Cloud navigateur et SHA** : 5 variantes de /api (normal, ui_safe, ui_full, operator et operator+ui_full) ; aucun gel, premier rendu sans clic, smartphone et transitions de session | Correctif du drawer [#390](https://github.com/AlbanAndrieu/fastapi-sample/pull/390) **fusionné** ; mesurer avec Chromium et confirmer /v2/version sur le binaire Cloud, sans attribuer build_revision=null à un succès |
| **E02** | **FinOps Cloud Nano** : limiter polling, reconstruction des sondes, profilage et fan-out ; établir baseline CPU, RAM, réplicas et latence avant/après sur fenêtres identiques | Optimisations **CODED** dont [#405](https://github.com/AlbanAndrieu/fastapi-sample/pull/405) fusionnée ; chiffres de consommation **NOT_MEASURED** ; [runbook](runbooks/fastapi-cloud-runtime-cost-guard.md) |
| **E03** | **Quality gate local-first au HEAD exact** : just ui-quick, tests ciblés, L2 puis L3, tests de contrat, contrôle des scripts et deux runs master réellement verts si fermeture de [#355](https://github.com/AlbanAndrieu/fastapi-sample/issues/355) souhaitée | CI bornée [#391](https://github.com/AlbanAndrieu/fastapi-sample/pull/391) et pytest mutualisé [#392](https://github.com/AlbanAndrieu/fastapi-sample/pull/392) **fusionnés** ; nouveaux résultats au SHA courant **NOT_RUN** |
| **E04** | **DNS / release / autorisation** : attester fastapi-sample.albandrieu.com et l’accès Cloudflare ; garder les frontières public/SERVICE/OWNER ; identifier la révision TrueNAS | DNS, Tunnel, règles et déploiement **propriétés de [Compose](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap.md)** ; [runbook de recette](runbooks/fastapi-truenas-owner-acceptance-20261029.md) ; pas d’apply implicite |

**Gate P0 :** E01 et E02 mesurés sur la version déployée, E03 sur la même révision, E04 sans nouvelle exposition. Tout verdict incomplet reste NOT_VERIFIED.

## P1 — Observabilité, réseau et interface

| ID | Action à réceptionner | État documenté et preuve de fin |
| --- | --- | --- |
| **E05** | **Couverture des sondes Cloud** : expliquer les slots éligibles, 16 warnings et preuves manquantes ; distinguer DENIED, STALE, UNKNOWN, FAILED et DOWN | Dernière baseline citée : 19/28 slots observés (67,9 %) et 2/28 healthy (7,1 %), **historique non actualisé** ; fraîcheur et échantillonnage sur Cloud à revérifier ; [runbook](runbooks/cloud-probe-evidence-coverage.md) |
| **E06** | **Gatus / Prometheus** : réconcilier catalogue, âge, exports, jobs absents et 401 attendu sur /metrics ; vérifier les 85 sondes historiques contre la configuration actuelle | 61 UP / 24 DOWN était un état **26/10**, non un diagnostic courant ; [acceptation](runbooks/fastapi-observability-acceptance.md) ; les jobs/exporters sont déployés par Compose |
| **E07** | **OWNER TrueNAS / mobile** : /health 200, /healthz cohérent, sessions autorisées LAN, refus WAN, détails et métriques privées absents en SERVICE | Recette 6/6, image active et clés/Access à attester sur l’instance réelle ; la sémantique de Keycloak challenge et Pyroscope ready doit être conservée ; [runbook](runbooks/fastapi-truenas-owner-acceptance-20261029.md) |
| **E08** | **Connexions TrueNAS ↔ Cloud / Cloudflare / Prometheus** : DNS/TCP/TLS/HTTP/auth et provenance par service, test extérieur et LAN sans faux positif | Connecteurs [#396](https://github.com/AlbanAndrieu/fastapi-sample/pull/396) **fusionnés** ; réception LAN et en production non démontrée ; [runbook](runbooks/truenas-cloud-connection-probes.md) |
| **E09** | **Accueil et cartes** : affichage utile dès le chargement, cache public expurgé, états de dégradation et non-régression mobile/clavier/lecteur d’écran | Météo fictive remplacée en code par Operations Overview ([#396](https://github.com/AlbanAndrieu/fastapi-sample/pull/396)) ; vérifier le runtime ; [runbook](runbooks/home-operations-transition.md) |
| **E10** | **Ressources et topologie** : heatmap OWNER CPU/RAM/FS/RX-TX, cAdvisor et pulse TrueNAS, filtres et identifiants canoniques | Prototype et réduction du réveil Cloud [#405](https://github.com/AlbanAndrieu/fastapi-sample/pull/405) **fusionnés** ; zéro ≠ absent ; CSS/mobile et provenance à réceptionner ; ne pas confondre container_fs et ZFS |

## P2 — Réduction de dette et extensions

| ID | Action à réceptionner | Condition de reprise |
| --- | --- | --- |
| **E11** | **Scripts, hooks et tests** : consolider les lanceurs pytest/quality, éliminer doublons Ruff/commitizen et vérifier prek/hk, worktrees/verrous après SIGKILL | Garder une gate canonique et des tests de contrat ; aucun contournement de hook pour produire un PASS |
| **E12** | **Contrats API et tracing** : RoutePolicy/JWT/JWKS pour HTTP, WebSocket et MCP ; traceparent / X-Nabla-Trace-ID entre FastAPI et Site Alban | Tests négatifs d’autorisation et compatibilité des consommateurs avant mode strict |
| **E13** | **Intégrations et maintien** : Renovate/Helm (automerge=false), Betterleaks/Trivy/CodeQL, DefectDojo, Sentry/Pyroscope, LiteLLM/OpenRAG | Inventaire et preuve par consommateur ; les scans actifs restent sous autorisation |
| **E14** | **Extensions observabilité** : fédération d’agrégats TrueNAS → Cloud, métriques ZFS dédiées et flux Akvorado attribuables | Source, droits, échantillonnage et fraîcheur démontrés ; aucune donnée réseau privée publique |

## Propriété et sources de vérité

- **FastAPI Sample** : collecteurs, DTO, interface /api, qualité Python/JS, cache de preuve, authentification serveur et réception runtime de l’API.
- **[nabla-compose](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap.md)** : Apps TrueNAS, pfSense, PostgreSQL, Gatus/Prometheus, DNS/Tunnel, secrets, déploiements et observations LAN.
- **[Site Alban](https://github.com/AlbanAndrieu/nabla-site-alban/blob/master/docs/homelab-roadmap.md)** : cartes Next.js, ReactFlow/C4, cache navigateur, UI OWNER/SERVICE. [Qualité site](https://github.com/AlbanAndrieu/nabla-site-alban/blob/master/docs/quality-roadmap.md).
- **[Bababou](https://github.com/AlbanAndrieu/nabla-site-bababou/blob/master/docs/roadmap.md)** et **[OpenClaw](https://github.com/AlbanAndrieu/nabla-openclaw/blob/master/docs/roadmap.md)** : leurs chantiers autonomes, notamment FinOps Vercel ; ne pas recopier ici.

**Documentation** : [index](README.md) · [incidents](incidents.md) · [backlog ancien à requalifier](engineering-backlog.md) · [historique complet avant le 13/11](archive/2026-11-13/engineering-roadmap-before-reconciliation.md). Les comptes rendus datés restent en archive ; les commandes dans les runbooks.
