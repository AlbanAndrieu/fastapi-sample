---
description: Faire converger le quality gate local et corriger ses erreurs
agent: fastapi-maintainer
---
Fais converger le quality gate local du dépôt sans utiliser GitHub Actions.

État avant gate :

!`git status --short`

Exécute exactement :

```bash
bash scripts/agent-quality-gate.sh --fix
```

Si le gate échoue ou réécrit des fichiers :

1. lis uniquement les erreurs pertinentes et le diff produit ;
2. corrige la cause racine, sans désactiver ni assouplir le contrôle ;
3. relance les tests ciblés concernés ;
4. relance la commande ci-dessus jusqu'à réussite ou jusqu'à rencontrer une
    dépendance réellement indisponible ;
5. vérifie `git diff --check`, `git diff` et
    `git status --short` ;
6. documente dans la roadmap toute validation impossible.

Ne lance aucun workflow GitHub. Ne prétends pas que le gate est vert si la
commande n'a pas terminé avec succès.
