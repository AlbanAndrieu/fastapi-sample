# Runbook — qualité locale bornée et verrou inter-agents

Les scripts `agent-quality-gate.sh` et `agent-publish.sh` partagent les
utilitaires `scripts/ci/quality-lock.sh` et `quality-timeout.sh`.
Ils ne désactivent aucun test, hook ou contrôle de sécurité.

## Concurrence

Chaque worktree détient un fichier de verrou sous son répertoire Git
(`agent-quality-gate.lock`). `flock -n` retourne immédiatement
`QG_LOCKED` (exit 75) si Claude Code, Codex ou un autre agent lance déjà
la qualité dans **ce même worktree**. Le descripteur reste ouvert : le
noyau libère le verrou à l'arrêt normal ou forcé, sans analyse du PID ni
suppression du fichier. Utiliser un worktree différent par agent.

Prérequis : util-linux `flock` sur Linux. Son absence provoque
`QG_LOCK_TOOL_MISSING` (exit 2), sans lancer la validation en parallèle.

**Migration depuis l'ancien répertoire de verrou :** si le chemin est encore
un répertoire, le script retourne `QG_LOCK_LEGACY_DIR` (75). Vérifier
d'abord qu'aucun agent ancien ne s'exécute. Sauvegarder son contenu si
nécessaire. Retirer ensuite *manuellement* l'ancien répertoire après
vérification ; ne jamais utiliser `git clean -fd` ni un effacement global
du cache de précommit. Le fichier de verrou moderne reste en place et ne
doit pas être supprimé pendant l'exécution d'un agent.

## Limites locales

| Variable | Par défaut | Portée |
| --- | ---: | --- |
| `QUALITY_STEP_TIMEOUT_SECONDS` | 900 | Hooks et contrôles généraux |
| `QUALITY_PYTEST_TIMEOUT_SECONDS` | 1800 | Suite pytest locale |
| `QUALITY_PRECOMMIT_TIMEOUT_SECONDS` | 600 | Un passage de correction automatique |
| `QUALITY_PUBLISH_TIMEOUT_SECONDS` | 2400 | Gate de publication avant le push |

Chaque budget est compris entre 1 et 3600 secondes. Le script utilise
`timeout --signal=TERM --kill-after=15s`. Un délai dépassé provoque
`QG_STEP_TIMEOUT` et code 124 ; SIGKILL provoque code 137. Tous les
autres codes d'erreur sont conservés et la gate échoue. Les journaux
compacts sont affichés à l'échec selon `QUALITY_LOG_TAIL`.

Ces budgets bornent une **commande exécutée**. Ils ne garantissent pas
l'absence de panne du système, de quota CI ou d'attente de runner GitHub.

## Validation locale, sans CI

```bash
bash -n scripts/ci/quality-lock.sh
bash -n scripts/ci/quality-timeout.sh
python -m pytest -q tests/unit/test_quality_lock_timeout.py \
  tests/unit/test_agent_quality_gate_contract.py \
  tests/unit/test_agent_publication_proof.py
bash scripts/agent-quality-gate.sh --fix
```

L1 valide les commandes synthétiques et la concurrence. L2 complète
la qualité sur un arbre propre ; L3 exige une preuve de publication liée
au HEAD exact. Un refus de verrou, une commande expirée ou une absence
d'outillage n'est jamais un PASS.
