# fastapi-sample — Agent Guide

## GitHub Actions credit-saving PR lifecycle

- Agents should create and retain pull requests as **Draft** while iterating, and run the targeted local `just`/quality-gate checks before requesting review.
- In ordinary reviewed PRs, do **not** use `[skip ci]`, `[ci skip]`, or `skip-checks: true`: these can leave required checks pending. **Exception:** when the owner explicitly requests zero-credit/local-first work, keep the PR Draft and use `[skip ci]` only for agent commits; mark hosted gates NOT_RUN and never merge before the required review gates are restored.
- `ready_for_review` must start the required CI; subsequent non-draft pushes run it again. Do not weaken SAST, SCA, DAST, secret scanning, or required branch protection to save minutes.
- Never mark a PR Ready automatically merely to burn credits. Only do so after explicit user direction or the repository's documented publication gate, and never merge without authorization.
- Keep generated PDFs (when uploaded) for at most **1 day**. Prefer no uploads on successful routine PR jobs and short-lived failure diagnostics.

## Agent FastAPI — démarrage local-first sans réseau

Pour un incident `/api` ou une reprise de PR, commencer par
`just agent-context ui` (ou `python3 scripts/agent-task-context.py --task ui`
si Just est absent). Ce préflight borne les chemins, suggère le skill
`local-first-quality` et sélectionne `just ui-quick` ; il ne lance
aucun réseau, navigateur, déploiement, installation ou CI. Pour les travaux
hors UI, passer `cloud`, `truenas`, `metrics`, `api` ou `quality`.
Conserver les règles de publication ci-dessous : `just ui-quick` = L1,
`agent-quality-gate.sh --fix` = L2 et `agent-publish.sh` = L3 sur
HEAD exact. Un résultat `L1 PASS` ne valide ni CI, ni runtime Cloud,
ni TrueNAS. Les commandes `mise run agent-loop/agent-pre-push` de
`nabla-compose` **n'existent pas dans ce dépôt et ne sont pas copiées**.

## Fast investigation protocol (load only when relevant)

Before a tool-heavy task, resolve the PR's immutable HEAD and check changed
paths once. Read the **relevant section only** of
`docs/engineering-roadmap.md` and one matching on-demand skill; never preload
the complete roadmap, every skill, all CI logs or broad repo trees by default.
Batch independent GitHub **reads**, then make one logical commit via
an expected-SHA update. If concurrent commits invalidate the lease, inspect
the *new diff*, not the entire repository. Never repeatedly poll check-runs.

API-only/no-checkout work: test the smallest exact-SHA snapshot when feasible,
declare missing full-gate proof explicitly, and retain `[skip ci]` when user
requests local-first to conserve CI credits. No security gates may be waived.

Issue hygiene: use the single manual-safe tracker #355 via
`scripts/ci/master_red_issue.py`; never create an issue or draft PR per run.
See the focused skill for exact SHA and two-green acceptance checks.

Documentation lifecycle: current roadmap = pending priorities and acceptance;
`docs/incidents.md` + runbooks = unique diagnostic history; finished changes
belong in code/tests/Git history. Prefer updating one canonical document and
removing obsolete duplicates rather than adding another narration.


## Master-red issue automation and bounded diagnosis

- Workflow owner: `.github/workflows/master-red-remediation.yml`.
  Treat [#355](https://github.com/AlbanAndrieu/fastapi-sample/issues/355)
  as the **only** current master-red issue; legacy SHA issues are preserved as
  superseded historical evidence, not evidence of fixes.
- The issue title, body and labels are human-curated. The bot may update
  **one** integrity-checked status comment, and close after two distinct,
  consecutive green master runs with no intervening manual drift.
  Never create per-SHA issues/draft PRs, and never close or reopen an issue
  a human has touched (even before enrollment): closing it stays a human call.
- CI: retrieve the failed job/step once at the exact SHA; prefer targeted
  offline tests over repeated remote reads or pipeline reruns.
- Never reduce scan coverage, leak detection, or branch/security controls
  to save tokens; distinguish actual local L1-L3 evidence from remote CI.

## Mission

Maintain this Python/FastAPI application with minimal, testable changes.

Prefer repository sources of truth over assumptions or duplicated documentation.

## Documentation ownership across Nabla repositories

`nabla-compose` is the single source of truth for pfSense/WebConfigurator
appliance recovery, Cloudflare Tunnel/Access operational routing and
self-hosted Sentry deployment/ingestion. `fastapi-sample` owns only its
application observers, cache/fan-out, health semantics, Sentry SDK/DSN
selection, logging and tests. Keep dated app incidents in `docs/incidents.md`.
Do not duplicate appliance shell commands or infrastructure route snapshots in
FastAPI docs; link to the `nabla-compose` runbooks. Retain existing application
documentation paths as compatibility entries when splitting ownership.
Do not move operational scripts back into this application repository.

## Mandatory execution protocol

This section is deliberately explicit so smaller models such as the OpenCode
workstation model can execute repository work reliably. Do not compress, reorder,
or silently skip these steps.

For every non-trivial repository task:

1. **Establish state before editing.** Run `git status --short`,
    `git branch --show-current`, and inspect the smallest relevant diff/files.
    Never assume a branch, PR, CI result, deployment state, or prior edit is still
    current.
2. **Protect `master`.** Never mutate the default branch. If the active PR was
    already merged or the requested branch no longer exists, create a new branch
    from current `master` before changing files.
3. **Read the plan.** Inspect the relevant section of
    `docs/engineering-roadmap.md`. Keep work inside the requested PR scope and
    record newly discovered residual work there.
4. **Load the task-specific skill before implementation.** Use OpenCode's
    `skill` tool for the matching entry in the skill-routing table below. Do not
    rely on remembered instructions when a repository skill exists.
5. **Inspect implementation and tests together.** Find the production code,
    closest tests, configuration, and callers before editing. For files above the
    maintainability thresholds, extract a cohesive responsibility rather than
    adding more unrelated code.
6. **Make one logical batch.** Prefer the smallest safe change. Preserve existing
    contracts unless the task explicitly requests a breaking change.
7. **Run focused validation first.** Execute the closest tests or static checks
    for the changed behavior before the repository-wide gate. If the checkout
    exists but dependencies or network are unavailable, run `just offline-l1`
    (Python AST, JSON, Shell and Draft-runner policy) as **L1-only** evidence;
    use `just p0` when pinned dependencies are already installed. Neither is
    equivalent to `just quality`, `just workflow-audit`, or publish-check.
8. **Converge the deterministic local gate.** Run
    `bash scripts/agent-quality-gate.sh --fix`. Fix root causes; never weaken,
    skip, or disable a formatter, lint, test, security, workflow, or size rule just
    to get green.
9. **Review before publication.** Inspect `git status --short`, `git diff`,
    and the staged/committed diff. Commit only the intended logical batch. In an
    explicitly requested no-GitHub-Actions/no-credit mode, use `[skip ci]`, keep
    the PR Draft, and do not dispatch or re-run remote workflows.
10. **Prove publishability locally.** With a clean committed tree, run
    `bash scripts/agent-publish.sh`. This is the canonical publication command;
    it invokes the strict quality gate and the scope-aware build checks. Never
    claim the local gate or publication proof passed unless the command actually
    completed successfully.

If a required local tool, dependency, network, LAN service, or checkout is
unavailable, continue with the strongest deterministic checks that are actually
possible, record the missing acceptance proof in the roadmap, and report the
limitation precisely. Do not substitute a guess or a remote CI run for missing
local evidence.

### Skill routing

Load only the skills needed for the current task, but load the matching skill
*before* editing when one of these triggers applies:

| Task trigger | Skill to load |
| --- | --- |
| FastAPI routes, dependencies, Pydantic/API behavior | `fastapi` |
| FastAPI Cloud runtime/deployment | `fastapi-cloud` |
| Homelab runtime status, migrations, live validation | `homelab-runtime-status` |
| Catalog/topology/runtime reconciliation | `homelab-service-contract` |
| CI failures, local-first gates, network/DNS outages, agent quality | `local-first-quality` |
| Pytest or contract-test changes | `pytest-contract-testing` |
| pfSense, PF, HAProxy, Snort, Unbound, Kea, pflow/IPFIX | `pfsense-api-debugging` |
| Redis lifecycle/cache integration | `redis-async-lifecycle` |
| Sentry diagnostics/workflow | `sentry-workflow` |
| Supabase/PostgreSQL design or performance | `supabase-postgres-best-practices` or `supabase` |
| Langfuse integration | `langfuse` |

When several rows apply, load the smallest useful set. A skill augments
`AGENTS.md`; it never overrides repository safety, branch, validation, or
publication rules.

## Repository bootstrap

Git hook configuration is versioned, but Git does not install repository hooks automatically after clone. On a new checkout, run:

```bash
mise run hooks
```

This installs the configured `pre-commit`, `commit-msg`, and canonical
`pre-push` quality-gate hooks. When normal GitHub Actions capacity is available,
CI provides an additional enforcement layer. During explicit local-first/no-credit
work, the strict local publication proof is the required merge evidence and the PR
must remain Draft until it is green.

## Sources of truth

Before changing behavior, inspect the relevant files:

- `README.md` — concise project quick start and canonical runtime entry points
- `pyproject.toml` — Python version, dependencies, and tool configuration
- `nabla/config_settings.py` — application settings
- `nabla/main.py` — FastAPI application
- `tests/` — expected behavior
- `scripts/` — repository quality and maintenance commands
- `.github/workflows/` — CI behavior
- `docs/README.md` — documentation map and canonical navigation
- `docs/incidents.md` — reusable incident evidence and recurrence rules
- `docs/engineering-roadmap.md` — canonical active roadmap
- `docs/` — focused architecture and operational runbooks

Do not duplicate information from these files into code or agent instructions.

## Tool and context efficiency

Load only the relevant skill and roadmap heading for each task; never preload
the entire backlog, all skills, complete logs, large generated artifacts, or
connector tool schemas. Keep all first-class tools available on demand.

1. Resolve the PR HEAD once; inspect `git status`, changed paths and
    the nearest source/tests, not the entire repository.
2. Batch independent **read-only** GitHub calls. Prioritize failing job
    and step logs before expanding full CI traces and artifacts.
3. Use one bounded logical patch/commit with optimistic expected-SHA
    update; reconcile changed files on concurrent edits instead of
    repeatedly retrying or polling the branch.
4. Validate exact SHA locally (`uv`, `just`, repository gate) where
    possible; otherwise run focused snapshot checks and state limitations
    explicitly. `[skip ci]` preserves credits, **not** security acceptance.
5. Preserve incident forensic evidence in `docs/incidents.md` and
    infrastructure ownership in `nabla-compose`; completed checklists
    belong in tests/code/Git history, pending long-tail work in
    `docs/engineering-backlog.md`.
6. Bot-generated GitHub issues must not overwrite human title, body,
    labels or state edits. An issue closes only on two consecutive
    successful master-red runs and never once a human touched it.

## Package management and task runners

Use `uv` for Python dependency/runtime management.

Use `justfile` as the preferred local-first task-runner frontend for routine
development and quality commands. Keep the existing `Makefile` available for
legacy Docker/Sphinx/specialist targets until a separate migration explicitly
removes it.

The repository scripts remain the canonical implementation of quality and
publication policy; Just recipes delegate to them rather than reimplementing
their logic.

Prefer:

```bash
uv sync
just --list
just test
just fix
just quality
just publish-check
```

Direct script equivalents remain supported for automation and diagnosis:

```bash
bash scripts/agent-quality-gate.sh --fix
bash scripts/agent-quality-gate.sh
bash scripts/agent-publish.sh
```

For retained legacy targets use `make <target>` or `just legacy <target>`.
Do not delete the Makefile as part of unrelated cleanup.

Do not introduce Poetry-based workflows unless the repository explicitly requires them.

## Development rules

- Make the smallest change that solves the requested problem.
- Prefer editing existing modules over creating new abstractions.
- Preserve backward compatibility unless explicitly asked otherwise.
- Follow existing Python naming and architecture.
- Use type annotations for public functions and FastAPI endpoints.
- Do not perform network, database, telemetry, or SDK initialization at module import time.
- Never log credentials, tokens, or secret values.
- Do not edit `.env`, `.env.local`, or `.env.secrets` unless explicitly requested.

## Validation

For a focused change, run the closest relevant formatter/linter or test first.

After one logical editing batch, use the repository-specific agent workflow before publishing:

```bash
bash scripts/agent-quality-gate.sh --fix
# Review the converged diff, then commit the intended logical batch.
bash scripts/agent-publish.sh
```

`agent-publish.sh` is the canonical final local publication command. It requires
a clean committed tree, calls `agent-quality-gate.sh --publish`, reuses an exact
HEAD/base/toolchain proof when valid, and runs the scope-aware Pylint/import/build
checks when application packaging is required.

`--fix` is intentionally convergent: deterministic pre-commit rewrites are retried for a small bounded number of passes and the rewritten editing tree is then validated. Do not publish a formatter-generated intermediate commit merely to discover the next deterministic rewrite.

The strict agent gate checks branch freshness, base-scoped acknowledgements for suspicious destructive truncations or complete large-file deletions, repository-local links in changed Markdown, executable bits for shebang scripts, modified-Python code-size limits, release/version consistency, and the complete pytest suite when Python/runtime/test dependencies are affected. Non-Python documentation/configuration-only changes may skip the full pytest suite after the canonical gate has validated them. When the gate script itself changed, focused shfmt/ShellCheck/bashate hooks run before pytest so gate defects fail early.

The canonical gate remains the shared formatter/linter/security orchestrator.
Normal mode is dirty-tree aware for iterative validation;
`scripts/agent-quality-gate.sh --publish` is the strict clean-tree gate used by
`scripts/agent-publish.sh`. Keep expensive Docker, Sonar, MegaLinter and
runtime/deployment checks in CI when CI is intentionally available. Do not use
`workflow_dispatch` as a substitute during an explicit no-credit/local-first
period.

## Mandatory agent publish policy

Agents must never publish changes immediately after editing files.

### Default branch is never a mutation target

Agents must never create, replace, delete, commit, push, or move a Git ref directly on `master`, including through GitHub API file actions. This prohibition also applies to trivial, documentation-only, CI, emergency, and one-line changes.

Every remote mutation must explicitly target a non-default branch created from the intended `master` revision, and repository changes must reach `master` only through a pull request. Agents must not merge that pull request unless the user explicitly asks them to do so.

Before every `git push` or other publication of a completed local batch:

1. Run `bash scripts/agent-quality-gate.sh --fix` after the complete logical
    editing batch; let deterministic rewrites converge instead of publishing each
    formatter pass.
2. Review the final converged diff and commit the logical batch once.
3. Verify `git status --short` is empty.
4. Run `bash scripts/agent-publish.sh`. Do not call lower-level publication
    checks instead unless debugging the wrapper itself.
5. Fix every formatter, linter, YAML, workflow, configuration, generated-file,
    lockfile, unit/contract-test, executable-bit, destructive-diff, build, or
    security-check failure caused by the change, then repeat from step 1.
6. Only publish after `agent-publish.sh` succeeds for the exact committed HEAD.

GitHub API file writes are an emergency/API-only fallback, not the preferred
OpenCode workflow. When a real checkout is available, edit and validate locally
so repository hooks and publication proofs cannot be bypassed.

Keep iterative agent pull requests as drafts until the strict local gate is green. Expensive CI may skip draft PRs while the deterministic preflight still runs. When `mise run hooks` has been run, the normal Git `pre-commit` hook validates commits and the `pre-push` hook invokes `scripts/agent-quality-gate.sh --publish`.

An API-only agent must not silently treat remote API writes as a way to bypass local hooks. If its runtime cannot obtain or execute a checkout, it must explicitly report that limitation, reproduce the closest deterministic validations available, keep the remote patch minimal, and inspect the resulting CI immediately. Batch files from one logical patch into one commit/tree whenever possible: every PR synchronize event can start or cancel runners. It must never claim that the local quality gate passed when it was not executed.

Never bypass repository hooks with `git push --no-verify`. Never weaken or disable formatter, lint, security, YAML, workflow, generated-file, or validation rules merely to make a push or CI build pass.

## Maintainability and file size

Before modifying a source file, assess both its size and its responsibilities.

- Python files above **400 lines** are a maintainability warning. Prefer extracting cohesive modules instead of adding unrelated responsibilities.
- Python files above **700 lines** must normally be refactored before significant new functionality is added, unless the file is generated, a migration, or inherently declarative.
- Functions above roughly **60 lines** should be reviewed for extraction; functions above **100 lines** should normally be refactored.
- Classes above roughly **250 lines** should be reviewed; classes above **400 lines** should normally be split by responsibility.
- Existing oversized modules are technical-debt candidates: when a requested change touches one, actively look for a safe opportunity to extract cohesive responsibilities rather than making the file larger.
- Configuration modules are not exempt merely because they contain many settings; split them by coherent domain when size and coupling justify it.
- Avoid module-level initialization that performs network calls, opens database connections, starts telemetry exporters, or initializes feature-flag SDKs. Prefer lazy factories, dependency injection, or FastAPI lifespan initialization.
- When using an API that replaces a complete file, never submit a partial file body. Fetch the complete current file, transform it, validate the result, then replace it.
- The repository enforces modified Python file size with `scripts/check_code_size.py`: warning above 400 lines and failure above 700 lines. Generated code and migrations are excluded explicitly.

Do not refactor unrelated code unless necessary for the requested change.

## External information

When behavior depends on a third-party API, framework, or library version, verify current official documentation rather than relying on memory.

## Completion

An agent must not declare work complete while any known residual, deferred validation, limitation, cross-repository follow-up, or unresolved risk has not been recorded in the canonical `docs/engineering-roadmap.md`.

Before reporting completion:

1. reconcile the final implementation and runtime evidence with `docs/engineering-roadmap.md`;
2. add or update a roadmap item for every known residual, including work intentionally deferred to another repository or deployment environment;
3. record the next acceptance proof needed to close each residual;
4. only then distinguish completed scope from remaining work.

CI green, a successful deployment, container `RUNNING`, TCP/HTTP reachability, or a partial functional check never waives this accounting requirement. If the roadmap cannot be updated, report the task as **not complete** and identify the missing roadmap entry.

Report:

1. what changed;
2. checks executed;
3. unresolved failures or risks and their corresponding roadmap entries.

### Measure before expanding CI

Run `python3 scripts/github-actions-usage.py --days 30` locally with authenticated `gh` to compare per-workflow job wall time and retained artifacts for the four active repositories. The inventory is read-only and uses GitHub REST; it is intentionally **not** scheduled in GitHub Actions to avoid consuming the very credits it audits. Job wall minutes are only an operational proxy, **not** invoiced minutes; rely on GitHub Billing for authoritative usage. Run `--repo NAME` to narrow scope or repeat it to select multiple repositories. Review the worst offenders before adding jobs or artifacts, keep PDF uploads at one day, and preserve mandatory security checks on Ready for review.
