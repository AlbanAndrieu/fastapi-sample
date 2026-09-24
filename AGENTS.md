# fastapi-sample — Agent Guide

## Mission

Maintain this Python/FastAPI application with minimal, testable changes.

Prefer repository sources of truth over assumptions or duplicated documentation.

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
   for the changed behavior before the repository-wide gate.
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

- `README.md` — project usage and architecture
- `pyproject.toml` — Python version, dependencies, and tool configuration
- `nabla/config_settings.py` — application settings
- `nabla/main.py` — FastAPI application
- `tests/` — expected behavior
- `scripts/` — repository quality and maintenance commands
- `.github/workflows/` — CI behavior
- `docs/` — detailed documentation

Do not duplicate information from these files into code or agent instructions.

## Tool and context efficiency

`AGENTS.md` is the repository-wide source of truth for agent policy. Keep `CLAUDE.md` and `.github/copilot-instructions.md` as thin adapters to this file. Treat `.github/instructions/` and `.agents/skills/` as task-specific, on-demand guidance; do not preload every instruction or skill.

Optimize the amount of context needed to obtain reliable evidence, not the agent's capabilities. Context efficiency must never be used to skip a necessary tool, test, security check, diagnostic, artifact, or deployment validation.

### Tool classes for this repository

**First-class — use without functional restriction when the task needs them, but do not preload their full schemas or output:**

- local repository tooling: `git`, `rg`, `git status`, `git diff`, `git ls-files`, `uv`, `mise`, and repository scripts;
- GitHub repository/PR/Actions/code-security tooling, including the Python CI, pytest, Ruff, Pylint, Bandit, MegaLinter, CodeQL, Docker and Trivy gates;
- the local `fastapi-sample` MCP/runtime diagnostics when the application is running;
- FastAPI Cloud deployment, environment inventory, runtime logs and production validation;
- Vercel deployment/status for the lightweight compatibility proxy;
- Sentry issue/error/trace diagnostics when investigating production or observability behavior.

**On-demand — keep available, but discover/load only for a relevant task:**

- direct TrueNAS and pfSense MCPs; prefer the application's read-only homelab/runtime abstraction first unless appliance-level evidence is required; whenever a task touches pfSense/Netgate, PF, HAProxy, Snort, pfBlockerNG, Unbound, Kea or pflow/IPFIX, first read `.agents/skills/pfsense-api-debugging/SKILL.md` and do not depend on prior-chat context;
- Prometheus and Grafana direct tooling;
- Supabase, Langfuse, Redis and other integration-specific skills/tools;
- GitLab tooling for the retained legacy Pages/mirror pipeline;
- FastAPI/MCP, Kubernetes, AWS/EKS, Terraform and other domain instruction files when the current files or task actually require them.

**Out-of-scope by default:**

- AWS/EKS and Terraform operations for ordinary FastAPI application work; the current repository has no active EKS/Terraform implementation;
- any global connector, plugin, MCP or skill not referenced by the current task or by an active repository integration.

Do not uninstall, disconnect, or remove a globally available integration merely to save context. An installed integration that is not discovered or invoked costs less project context while remaining available for other repositories and future tasks.

### Targeted discovery and reuse

- For MCPs/connectors, discover only the few functions required for the current operation instead of loading the connector's complete schema. Reuse already discovered functions during the same task.
- Reuse previously fetched files, response resources, run/job identifiers, diffs and API results when they are still current; do not repeat an equivalent call without a reason.
- Prefer specialized operations such as PR metadata, changed filenames, a single file patch, workflow jobs or job steps over broad repository/REST responses.
- Fetch the smallest useful file fragment, diff, log range or result set first. Expand progressively only when the targeted evidence is insufficient.
- Do not avoid a first-class tool because its response may be large. Narrow the request first; if complete evidence is required, retrieve it.

### Repository context

Start investigation with the smallest local views that can answer the question: `git status --short`, `git diff --stat`, `git diff`, `rg`, `git ls-files`, then explicitly relevant files or line ranges. Avoid recursive repository reads, giant PR diffs, generated artifacts, lockfiles and large documents unless the task actually requires their complete contents.

When an API can return a changed-file list and per-file patches, prefer that progression over fetching an entire large PR patch. When a large file must be replaced through an API, fetching its complete current body is required by the file-replacement safety rule below.

### CI, deployment and observability evidence

Inspect failures progressively:

1. workflow/check status;
2. failed job;
3. failed step;
4. targeted job/step logs;
5. complete logs, artifacts, reports, traces, screenshots or videos only when the narrower evidence does not explain the failure or the richer artifact is itself the relevant evidence.

Prefer the compact local agent-gate output over remote CI logs. When CI still fails, fetch the failing workflow, then the failing job/step, then only the relevant log tail; expand to complete logs or artifacts only when that evidence is insufficient.

For Playwright, Cypress or other E2E failures, preserve existing coverage. Fetch reports, traces, screenshots and videos when they materially help; for difficult failures, use the complete artifact rather than guessing.

For FastAPI Cloud, Vercel, Sentry and other operational platforms, prefer narrow status fields and bounded/relevant logs before full deployment/event payloads. This is a response-size policy, not permission to weaken runtime diagnosis.

Do not poll workflow, deployment, check, job or observability status in a tight loop. Read once, continue other useful work, and revalidate when the result can materially change the next action. A requested final CI/deployment verification is mandatory even when intermediate polling is avoided.

## Package management

Use `uv`.

Do not introduce Poetry-based workflows unless the repository explicitly requires them.

Prefer:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

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

The strict agent gate checks branch freshness, suspicious destructive truncations or complete large-file deletions, executable bits for shebang scripts, modified-Python code-size limits, release/version consistency, and the complete pytest suite when Python/runtime/test dependencies are affected. Non-Python documentation/configuration-only changes may skip the full pytest suite after the canonical gate has validated them. When the gate script itself changed, focused shfmt/ShellCheck/bashate hooks run before pytest so gate defects fail early.

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
