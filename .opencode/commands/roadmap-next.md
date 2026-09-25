---
description: Prendre le prochain item roadmap finissable avec les gates locaux
agent: fastapi-maintainer
---
Travaille sur la prochaine amélioration finissable de fastapi-sample.

État actuel :

Branch:
!`git branch --show-current`

Status:
!`git status --short`

Diff stat:
!`git diff --stat`

Suis strictement `AGENTS.md`.

1. Lis la section pertinente de `docs/engineering-roadmap.md`.
2. Choisis un seul item de plus fort levier qui peut être avancé sans dépendre
    d'un service actuellement indisponible.
3. Charge avec l'outil `skill` tous les skills requis par la table de
    routage avant de modifier le code.
4. Inspecte les tests et appelants avant l'implémentation.
5. Implémente le plus petit lot cohérent.
6. Lance les tests ciblés.
7. Lance `bash scripts/agent-quality-gate.sh --fix` et corrige les
    erreurs jusqu'à convergence.
8. Mets à jour la roadmap et résume les preuves exécutées et celles encore
    différées.
9. Ne publie et ne lance aucun workflow distant de ta propre initiative.
