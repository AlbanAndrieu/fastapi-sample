---
description: Relire le diff local avec le subagent read-only
agent: quality-reviewer
subtask: true
---

Relis le diff local ci-dessous sans modifier le dépôt.

Branche :
!`git branch --show-current`

État :
!`git status --short`

Statistiques :
!`git diff --stat`

Vérification whitespace/conflits :
!`git diff --check`

Diff :
!`git diff --no-ext-diff --unified=3`

Applique `AGENTS.md` et charge les skills pertinents avec l'outil
`skill`. Rapporte d'abord les bugs/régressions/sécurité, puis les tests
manquants et enfin la maintainability. Ne propose pas de désactiver un gate.
