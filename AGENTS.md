# fastapi-sample — Agent Guide

## Mission

Maintain this Python/FastAPI application with minimal, testable changes.

Prefer repository sources of truth over assumptions or duplicated documentation.

## Repository bootstrap

Git hook configuration is versioned, but Git does not install repository hooks automatically after clone. On a new checkout, run:

```bash
mise run hooks
```

This installs the configured `pre-commit`, `commit-msg`, and canonical `pre-push` quality-gate hooks. CI remains the authoritative enforcement layer because local hooks can be absent or explicitly bypassed.

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

- direct TrueNAS and pfSense MCPs; prefer the application's read-only homelab/runtime abstraction first unless appliance-level evidence is required;
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

Before considering a substantial change complete, and always before publishing repository changes, run:

```bash
bash scripts/quality-gate.sh
```

The canonical gate validates files touched by the branch plus staged, unstaged, and untracked working-tree files through the repository `pre-commit` stage. Fix every formatter, linter, YAML, workflow, configuration, generated-file, lockfile, or security failure reported by the configured hooks. Re-run until the gate exits successfully and `git status --short` is empty.

Project-specific tests and expensive build/deployment checks remain in their native commands and CI; do not duplicate them inside the shared publication orchestrator.

## Mandatory agent publish policy

Agents must never publish changes immediately after editing files.

### Default branch is never a mutation target

Agents must never create, replace, delete, commit, push, or move a Git ref directly on `master`, including through GitHub API file actions. This prohibition also applies to trivial, documentation-only, CI, emergency, and one-line changes.

Every remote mutation must explicitly target a non-default branch created from the intended `master` revision, and repository changes must reach `master` only through a pull request. Agents must not merge that pull request unless the user explicitly asks them to do so.

Before every `git push`, GitHub API file update, or other remote repository mutation:

1. Run `bash scripts/quality-gate.sh` from a local checkout whenever shell access is available.
2. Fix every formatter, linter, YAML, workflow, configuration, generated-file, lockfile, or security-check failure caused by the change.
3. If the gate modifies files, review and commit those changes.
4. Run `bash scripts/quality-gate.sh` again until it exits successfully with a clean working tree.
5. Verify `git status --short` is empty.
6. Only then publish the changes.

When `mise run hooks` has been run, the normal Git `pre-commit` hook validates commits and the canonical `pre-push` hook invokes the same `scripts/quality-gate.sh` automatically before push.

An API-only agent must not silently treat remote API writes as a way to bypass local hooks. If its runtime cannot obtain or execute a checkout, it must explicitly report that limitation, reproduce the closest deterministic validations available, keep the remote patch minimal, and inspect the resulting CI immediately. It must never claim that the local quality gate passed when it was not executed.

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

Report:

1. what changed;
2. checks executed;
3. unresolved failures or risks.
