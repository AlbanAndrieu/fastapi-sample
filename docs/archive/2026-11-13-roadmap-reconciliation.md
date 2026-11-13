# Réconciliation de la roadmap d'ingénierie — 13 novembre 2026

> **Archive de décision, aucune procédure à relancer.** La version détaillée précédente est consultable [sur le commit master avant consolidation](https://github.com/AlbanAndrieu/fastapi-sample/blob/dd44c23c9ad365d06ef60b6b326633769b3f2311/docs/engineering-roadmap.md) ; les anciennes snapshots d'octobre restent sous [archive du 29/10](2026-10-29/engineering-roadmap-before-consolidation.md).

## Pourquoi la réconciliation

Le document actif comportait des preuves de tests et d'incidents au 26–31 octobre au milieu de correctifs fusionnés après le 11 novembre. Cela rendait difficile la distinction entre livrable `CODED`, recette `ACCEPTED` et constat daté `NOT_VERIFIED`.

## Transferts effectués

- Tableau de décision inter-dépôts : [portfolio Compose](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap-portfolio.md).
- `#382`, `#383`, `#390` (écran et gel), `#396` (fin de la météo démo), `#418` (tri cAdvisor), `#419` (budget Nano) : **fusionnés au code**, non replanifiés comme de nouvelles fonctionnalités ; leurs critères de recette subsistent dans F01, F02, F06 et F07.
- Historique des 85 moniteurs, 61 UP/24 DOWN, freezes Cloud et bugs de l'ancienne version : restent des **observations datées**, pas des alarmes actuelles.
- `nabla-compose` garde la responsabilité des mutations TrueNAS, pfSense et Cloudflare ; aucune action `--apply` n'est transférée à FastAPI.
- Le [backlog ancien](../engineering-backlog.md) n'est pas supprimé : chaque entrée doit être requalifiée à la lumière du code et du runtime avant d'être activée.

## Gardes de validation

Une PR fusionnée ne prouve ni la présence de son SHA en Cloud, ni les économies CPU, ni la santé TrueNAS. Garder les checklists opérationnelles dans les [runbooks](../README.md), les incidents dans [le registre](../incidents.md), et le travail restant dans la [roadmap active](../engineering-roadmap.md).
