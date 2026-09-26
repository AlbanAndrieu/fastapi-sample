---
description: Valider localement un HEAD propre avant publication
agent: fastapi-maintainer
---
Prépare le HEAD courant à une publication locale sûre.

Commence par vérifier :

```bash
git status --short
git branch --show-current
```

Refuse de continuer si la branche est `master` ou si l'arbre contient des
modifications non commitées qui ne font pas partie du lot prévu.

Si nécessaire, fais d'abord converger :

```bash
bash scripts/agent-quality-gate.sh --fix
```

Après revue et commit du lot logique, avec un arbre propre, exécute la commande
canonique :

```bash
bash scripts/agent-publish.sh
```

Si elle échoue, corrige la cause racine et recommence à partir du quality gate.
N'utilise jamais `--no-verify`. En mode sans crédits GitHub Actions, ne
déclenche aucun workflow distant et conserve la PR en Draft.
