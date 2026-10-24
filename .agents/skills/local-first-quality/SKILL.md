---
name: local-first-quality
description: >-
  Fast, exact-HEAD Python/CI security validation without wasting GitHub Actions
  credits; never weaken quality gates.
---
# Local-first quality (canonical task-specific skill)

`AGENTS.md` owns repository safety; the only publication authority is
`scripts/agent-publish.sh`. Load this skill **on demand** for CI,
agent efficiency, missing DNS or GitHub snapshot validation.

## Evidence levels
| L0 | Inspection only | Not tested |
| L1 | Focused test/syntax on exact files | Narrow check only |
| L2 | Changed-file hooks, formatting and security converge | Local proof |
| L3 | Clean exact HEAD, `scripts/agent-publish.sh` succeeded | Full local gate |

Never describe L0–L2 as full CI/L3. Missing dependencies/tools,
remote runtime or DAST = **NOT_RUN**.

## Shell interactif et isolation Python des worktrees

**P0 : ne jamais utiliser set -euo pipefail directement dans le
terminal interactif de l'opérateur (Bash ou zsh).** Un échec peut
fermer ce terminal. Exécuter toute séquence multi-commandes dans un
processus enfant : un script versionné exécuté avec bash, ou un
heredoc cité transmis à bash. Refuser toute exécution avec source
avant d'activer set -Eeuo pipefail. Tester qu'un échec arrête la suite
sans fermer le shell parent. Fournir un bloc opérateur indépendant
du répertoire courant, seulement pour les étapes inaccessibles à l'agent.

**Python FastAPI : 3.13** (mise.toml : 3.13.17).
- La source de vérité est pyproject.toml + uv.lock.
- Chaque agent possède **une .venv dans son propre worktree** :
  aucun partage de .venv ou de VIRTUAL_ENV entre agents.
- **Seul le cache de téléchargement uv est partagé**, par défaut
  $HOME/.cache/uv ; ne pas mutualiser des paquets installés.
- Choisir le Python du worktree explicitement, pas python3 du PATH.
  Un Python 3.14 global ou des dépendances absentes donnent BLOCKED,
  jamais un PASS ni une dérive de test.
- Ne pas lancer pip install global, mise install global, direnv allow
  ou source .envrc pendant un contrôle automatique ; la configuration
  de shell peut charger des secrets et provoquer des installations.
- scripts/agent-worktree-python.sh --check est **sans mutation**
  et son comportement par défaut. --sync déclenche volontairement
  uv sync --locked --python 3.13.17 dans la .venv locale.
  Cette synchronisation peut télécharger des dépendances ; elle
  n'écrit pas uv.lock ni n'installe le Python manquant.
- L1 ciblé précède L2 puis la gate L3 complète. Déclarer NOT_RUN
  pour les validations impossibles dans l'agent.

## Minimal loop
1. Resolve current branch, PR HEAD and base once. Inspect changed files,
    immediate tests, failing CI job/step only; avoid giant GitHub diffs,
    full roadmap and unrelated skills.
2. Keep changes in one logical patch; use `uv` / `just`. For a real
    checkout run targeted tests → `bash scripts/agent-quality-gate.sh --fix`
    → review diff → clean commit → `bash scripts/agent-publish.sh`.
3. When DNS/clone is unavailable, use an immutable cached Git snapshot
    with `scripts/agent-source-snapshot.sh`; otherwise materialize exact
    GitHub file bytes needed for focused tests. Don't invent a green L3.
4. In no-credit mode use `[skip ci]`, stay Draft and avoid repeated
    DAST/Sonar/MegaLinter runs. Never disable Betterleaks/Trivy Critical,
    pre-commit, pytest, CodeQL or any required security scan.
5. Publish with expected-SHA concurrency guard, one batch. On conflict,
    reread only concurrently changed files. Recheck the published SHA once.

## GitHub issue hygiene (one source of truth)
`.github/workflows/master-red-remediation.yml` and
`scripts/ci/master_red_issue.py` update only the bot-owned status comment
in [#355](https://github.com/AlbanAndrieu/fastapi-sample/issues/355).
Do **not** create issues/PRs per SHA, or mutate title/body/labels.
Before first enrollment, compare the reviewed `updated_at`, historical
manual issue events **and human comments**; afterwards verify fingerprint,
manual events and status-comment integrity.
Close only after two consecutive green master-red workflow numbers;
human edits prohibit auto-reopen. Test with
`python3 -m unittest tests.unit.test_master_red_issue -v`.

## Speed / token budget
- Begin with `PR HEAD + changed paths + one failing job/step`; batch independent reads.
- Avoid repeated CI polling, full 20k-line logs, GitHub-wide issue searches,
  large PR diffs and full skills catalog loads when an exact path is known.
- One atomic patch, then only focused offline tests. Fetch a new HEAD once,
  and inspect only failed checks; do not create placeholder remediation PRs.
- Preserve actual results: `PASS` / `FAIL` / `NOT_RUN` / `INCOMPLETE`.
  Tool/network access and CI outcomes must never be inferred as successes.

## User-facing communication (ASD-STE100-inspired)
- Write in the user's language. Apply the principles of ASD-STE100 (Simplified
  Technical English) to clarity and consistency; do not claim formal compliance.
- Use short, simple, direct sentences. Prefer the active voice.
- Give **one action per numbered procedure step**. Put its expected result in
  a separate sentence. Do not combine commands or actions in one step.
- Use **one consistent term for each concept**. Avoid unnecessary synonyms,
  vague pronouns, jargon and decorative wording.
- Name the exact file, command, endpoint, environment variable or PR when
  relevant. Separate facts, actions, results and remaining limitations.
- Report what was actually tested. Use `PASS`, `FAIL`, `NOT_RUN` or
  `INCOMPLETE` without changing their meanings.

## Documentation
Read the current `docs/engineering-roadmap.md` topic only. Long-tail
unchecked work in `docs/engineering-backlog.md` needs re-triage;
completed narratives are Git history. Preserve unique failure signatures
and recovery commands in `docs/incidents.md` or `nabla-compose` runbooks.
Report exact SHA, executed checks and residual `NOT_RUN` work.
