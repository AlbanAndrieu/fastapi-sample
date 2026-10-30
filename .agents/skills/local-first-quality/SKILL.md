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

## Optimisation FastAPI : routage et preuves L0–L3 (Compose 30/10/2026)

Ce projet réutilise **les principes**, pas les commandes incompatibles, de
`nabla-compose` : `agent-context`, sélection d'un seul test ciblé, revue des
changements automatiques et gate de publication exécutée une fois.
`nabla-compose` propose `mise run agent-loop/agent-pre-push` ;
**FastAPI conserve** `scripts/agent-quality-gate.sh --fix` et
`scripts/agent-publish.sh` comme sources d'autorité. Ne pas créer une seconde
quality gate ou installer de nouveaux outils pour ce routage.

| Niveau | FastAPI : commande | Preuve maximale |
| --- | --- | --- |
| **L0** contexte | `just agent-context ui` ou `python3 scripts/agent-task-context.py --task ui --json` | Inspection ; `NOT_RUN` pour les tests |
| **L1** UI rapide | `just ui-quick` (Node déjà disponible, sans npm install) | Contrats JS ciblés seulement |
| **L1** API ou système | le test ciblé indiqué par `agent-context`, dans le Python du worktree | Contrat ciblé seulement |
| **L2** convergence | `bash scripts/agent-quality-gate.sh --fix`, puis revue du diff | Gate local de l'arbre en cours, pas L3 |
| **L3** publication | commit propre puis `bash scripts/agent-publish.sh` | Gate locale complète au SHA exact |

`agent-context` fonctionne sans réseau, navigateur, CI ni installation. Il
signale la base absente et limite la liste des chemins; **il n'infère pas
l'état d'une PR depuis le checkout**. Vérifier l'état et le HEAD distant
une fois avant toute mutation. Pour une PR contenant plusieurs sujets,
préférer `--task ui|cloud|truenas|metrics|api|quality` au routage `auto`.
Le routage choisit **un point d'entrée**, jamais une dispense de suite
complète en L3.

**Incident UI spécifique :** lorsque `/api?ui_safe=1` fonctionne et que
`/api?ui_full=1` reste sur `Loading`, concentrer L1 sur le bootstrap
ESM, les réécritures DOM et `MutationObserver`. Comparer
`main_thread_unresponsive`, `ui_loading_without_content`,
`http_access_restricted` et `sampled` avant de changer la collecte
réseau. Le contrat `readOnlyDiagnostics=true` ne prouve ni OWNER ni
la disponibilité des sondes internes. Le navigateur Cloud doit rester
une recette **opt-in** ; ne pas le lancer pour chaque changement de texte.

**Mode GitHub API sans checkout :** utiliser des lectures ciblées sur le HEAD
sélectionné et une mutation avec blob SHA attendu. Reconstituer le test exact
dans un répertoire jetable si l'environnement permet de l'exécuter ; sinon
rester à `L0` / `L1 partiel` et annoncer `L2/L3 NOT_RUN`. Un test de
présence de chaînes ne prouve pas le fonctionnement de Chromium ou de FastAPI.
Ne pas multiplier les commits, relances CI, journalisations et recherches
GitHub pour obtenir artificiellement des preuves.

**Contrats multi-repo :** ne pas recopier les secrets, ressources réseau,
Docker/HAProxy ni la roadmap de `nabla-compose` vers FastAPI.
Consulter les chemins Compose précis, et conserver ses contraintes
TrueNAS/Vaultwarden/ZFS et les skills du domaine. Tout skill externe nécessite
validation explicite avant installation. L'absence d'accès LAN ne bloque pas
les tests UI locaux, mais interdit de déclarer une recette TrueNAS `PASS`.

## Minimal loop
1. Run `just agent-context ui` (or select another task). Resolve the PR
    HEAD and base once. Inspect only the changed files and the nearest tests;
    avoid broad diffs, full roadmaps and unrelated skills.
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
