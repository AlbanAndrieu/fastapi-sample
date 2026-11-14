# Réconciliation Backstage V2 et roadmap — 14 novembre 2026

> Archive de décision, aucune procédure à relancer. La [roadmap active](../engineering-roadmap.md) conserve les tâches F01–F12.

## Sources de vérité

- **[Compose #365](https://github.com/AlbanAndrieu/nabla-compose/pull/365)** est fusionnée : les descripteurs Backstage définissent les identités, titres, types, tags, propriétaires et dépendances. Les extensions x-nabla.exposure et x-nabla.runtime projettent les intentions et liaisons runtime. L'exposition déclarée n'est pas une observation.
- **[FastAPI #424](https://github.com/AlbanAndrieu/fastapi-sample/pull/424)** est fusionnée : ses routes consomment le catalogue V2. Le snapshot embarqué n'est qu'un cache froid, sans nouvelle autorité.
- **[Portefeuille H](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap-portfolio.md)** : la priorité arbitrée est **H02/G1 → H01 → H05**, suivie de H17 ; FastAPI F11 est le travail applicatif de H17.
- **Site Alban** : le retrait des vues et endpoints legacy reste bloqué jusqu'à la recette des consommateurs.

## Décalage constaté le 14 novembre

Le snapshot FastAPI et le catalogue généré de Compose présentaient tous deux **205 entités**, mais des révisions différentes :

| Source | catalogRevision |
| --- | --- |
| Compose master | sha256:9fb25382454bb4b2bec4fe67144c1f38270a3ddb416238fafe17ca46a6abc9be |
| Snapshot FastAPI avant synchronisation | sha256:4a68e9e5ae4b7ca23782f4b256061ba8440d7ab9635df9ef13e41ee4300ac8de |

**139 entrées x-nabla.runtime** différaient ; les identités, métadonnées et règles d'exposition étaient inchangées. Le script de mise à jour valide le digest du graphe avant remplacement atomique. La présence du snapshot dans Git ne prouve **pas** sa présence sur FastAPI Cloud ou TrueNAS.

## Répartition des affichages

| Vue | Données autorisées | Ne pas afficher ou inférer |
| --- | --- | --- |
| Anonyme, /api/ui/services | nom validé, kind, spec.type, jusqu'à trois metadata.tags, état de santé résumé et frais | URL/IP/port, owner, entityRef, backend, exposition réelle, sondes privées |
| OWNER | catalogue V2 validé, relations et intentions déclarées, observations distinctes par source | une disponibilité verte déduite d'une simple intention public ou d'un scrape Gatus UP |
| Site Alban | graph V2 allowlisté et santé issue de la même catalogRevision | informations provenant de l'observateur privé |

Les verdicts DENIED, NOT_RUN, STALE et NO_SAMPLE ne sont pas DOWN. Les informations de statut et les intentions de déploiement ont des sources distinctes.

## Conditions de réception ouvertes

1. Comparer la révision de Compose et celle réellement servie sur /api/site/catalog/v2, /api/site/health/v2, /api/homelab-services et /sickz à **SHA et date connus**.
2. Valider les cartes services sur mobile et desktop, le filtrage des tags et l'absence de fuite de l'interface anonyme.
3. En cas d'indisponibilité du catalogue, ne présenter que les noms approuvés et une santé UNKNOWN si les preuves ont expiré ; pas de fan-out public supplémentaire.
4. Migrer les consommateurs du Site Alban avant de retirer /api/homelab-services et les fichiers legacy côté Compose.
5. Archiver les essais et incidents avec horodatage et SHA. Ne pas rouvrir les anciens E01–E14.

Ce document est une archive. L'état des priorités est dans la [roadmap active](../engineering-roadmap.md).
