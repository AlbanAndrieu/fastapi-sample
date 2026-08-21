# FastAPI Sample — Agent Guide

Use this file as the canonical, tool-neutral entry point for Cursor, OpenCode, Codex, Copilot, and other coding agents.

## Project map

- Python 3.12 FastAPI service; ASGI app: `nabla.main:app`.
- Package manager: `uv`; lockfile: `uv.lock`.
- Core code: `nabla/`; tests: `tests/`; CI: `.github/workflows/`.
- MCP: inbound FastMCP plus outbound MCP clients.
- Runtime integrations include PostgreSQL, Redis, Sentry, Logfire, Datadog, Unleash, Statsig, Langfuse, and LiteLLM.

## Mandatory workflow

1. Inspect only the files needed for the task; do not preload large docs or unrelated rules.
2. Keep runtime dependencies used during `import nabla.main` in `[project].dependencies`; dependency groups are additive profiles, not a substitute for runtime requirements.
3. Never perform network calls, DB connections, feature-flag initialization, or telemetry exporter startup at module import time. Use lazy factories or FastAPI lifespan.
4. Any unexpected Pytest failure must fail CI. Do not implement failure-rate exceptions.
5. Tests must be order-independent and must not require external services unless explicitly integration tests.
6. When changing application wiring, add or run an ASGI smoke test that creates `TestClient(app)` and calls a concrete route such as `/api` or `/health`.
7. Before every push run `bash scripts/quality-gate.sh`; fix all failures and rerun until the working tree is clean. Never use `--no-verify`.
8. Use safe Ruff fixes only by default; do not apply `--unsafe-fixes` without reviewing the proposed changes.

## Maintainability

- Treat Python files over 400 lines as a warning and over 700 lines as refactor candidates before significant additions.
- Prefer cohesive modules and dependency injection over large configuration/service modules.
- When an API replaces a whole file, always fetch the complete current file before writing it back.

## Validation shortcuts

```bash
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest -q --maxfail=1
bash scripts/quality-gate.sh
```

For FastAPI Cloud runtime parity:

```bash
UV_PROJECT_ENVIRONMENT=.venv-runtime uv sync --frozen --no-default-groups
.venv-runtime/bin/python -c "import nabla.main"
rm -rf .venv-runtime
```

## Context loading

Load specialized material only when relevant:

- `.agents/skills/` — on-demand workflows and domain guidance.
- `.github/instructions/` — Copilot path-specific instructions.
- `.cursor/rules/` — Cursor path-scoped adapters.
- `README.md` and `docs/` — architecture or operational detail when the task needs it.

Do not duplicate large guidance across agent-specific files. If instructions conflict, prefer this file and the repository's executable configuration/tests over prose documentation.
