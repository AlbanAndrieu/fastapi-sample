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
