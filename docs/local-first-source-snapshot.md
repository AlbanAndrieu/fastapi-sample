# Validation local-first depuis un cache Git

Ce runbook est destiné aux agents lorsque `github.com` ou le DNS externe est
indisponible. Il ne remplace pas une quality gate et n'autorise pas le merge.

## Préconditions

- Un dépôt Git local **déjà présent** contenant le commit exact demandé et la
  base de comparaison. Un SHA GitHub connu n'implique pas que l'objet soit
  présent dans le cache.
- Les outils `git`, `bash`, `uv` et les dépendances des contrôles installées
  localement. Aucun `git fetch`, `git clone` réseau ni `uv sync` implicite.
- Ne jamais utiliser une archive téléchargée non vérifiée comme preuve d'un
  checkout exact-HEAD.

## Matérialiser et vérifier

Exemple avec un cache préexistant ; adapter les chemins et SHA :

```bash
SOURCE="$HOME/src/fastapi-sample"
HEAD_SHA="$(git -C "$SOURCE" rev-parse HEAD)"
SNAPSHOT="$(mktemp -d)/checkout"
bash scripts/agent-source-snapshot.sh "$SOURCE" "$HEAD_SHA" "$SNAPSHOT"
cd "$SNAPSHOT"
test "$(git rev-parse HEAD)" = "$HEAD_SHA"
test -z "$(git status --porcelain)"
git cat-file -e "origin/master^{commit}"
git merge-base --is-ancestor origin/master HEAD
```

La copie provient des objets Git commités, pas du worktree source. Ne pas déclarer
une validation du HEAD de PR si `HEAD_SHA` est simplement celui d'un cache obsolète :
comparer avec la métadonnée courante de la PR avant de lancer les gates.

## Valider, sans supprimer les contrôles

```bash
bash -n scripts/agent-source-snapshot.sh
bash -n scripts/run-pytest-compact.sh
uv run --no-sync pytest -q tests/unit/test_agent_source_snapshot.py tests/unit/test_compact_pytest_runner.py
bash scripts/agent-quality-gate.sh --fix
bash scripts/agent-quality-gate.sh
bash scripts/agent-publish.sh
```

Exécuter les contrôles de sécurité, de navigateur et DAST requis dans leurs
environnements adaptés : **SAST, BetterLeaks, Playwright et ZAP** ne sont
jamais réputés PASS parce que le réseau ou l'environnement manque. Garder
leurs traces/logs complets et une sortie agent concise.

## Matrice de preuve

Consigner dans la PR : SHA HEAD, SHA base, environnement, version des outils,
périmètre des tests et états `PASS`, `FAIL` ou `NOT RUN` pour
pytest, Ruff/pre-commit, SAST, BetterLeaks, Playwright, ZAP et build/smoke.
Un statut CI absent signifie **NOT RUN**, pas PASS.

En cas de SHA manquant dans le cache : arrêter le snapshot (fail closed),
obtenir une source par un canal autorisé et vérifiable, puis recommencer.
