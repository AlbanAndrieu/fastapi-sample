# fastapi-sample — Agent Guide

This file is the canonical repository-wide instruction entrypoint for Codex, OpenCode, Cursor, and Copilot. Keep it concise; load deeper documentation only when the task requires it.

## Project map

- Python 3.12+ FastAPI service. Main ASGI app: `nabla.main:app`.
- Runtime entrypoints: `server_app.py`, `server_all.py`, `server_mcp.py`.
- API and integration code: `nabla/api/`, `nabla/integrations/`, `nabla/mcp/`, `nabla/deepagents/`.
- Configuration: `nabla/config_settings.py` plus cohesive settings modules under `nabla/config/` when present.
- Tests: `tests/`.
- CI: `.github/workflows/`.
- Package manager and lockfile: `uv`, `uv.lock`.

## Default workflow

1. Inspect the smallest relevant set of files before editing.
2. Prefer focused changes over broad rewrites.
3. Run the narrowest useful validation first, then the repository quality gate before pushing.
4. Never hide, downgrade, or convert test/lint/security failures into success.
5. Keep external services disabled or mocked in unit tests; unit-test collection/import must not make network calls.

Useful commands:

```bash
uv sync --frozen
uv run pytest tests/path/to/test.py -q
uv run ruff check <changed-files>
uv run ruff format --check <changed-files>
bash scripts/quality-gate.sh
```

## FastAPI runtime invariants

- Import success is not enough: changes to app construction, middleware, routing, lifespan, MCP mounts, or configuration must exercise the ASGI application with `TestClient` or an equivalent smoke test.
- `/api` must remain reachable and return HTTP 200 in the startup smoke test.
- MCP mounts must not shadow ordinary FastAPI routes. Streamable HTTP is exposed under its configured MCP path.
- Do not perform network calls, DB connections, telemetry startup, or feature-flag SDK initialization at module import time. Use lazy factories or lifespan hooks and honor enable/disable settings.

## Python conventions

- Use modern Python 3.12 typing (`X | None`, `list[str]`, etc.).
- Prefer small cohesive modules, explicit dependencies, and typed boundaries.
- Use `SecretStr` or equivalent for secrets and never log secret values.
- Do not add significant responsibilities to Python modules already above the repository size thresholds; extract cohesive modules instead.

## Tests and CI

- Every Pytest failure is a CI failure. Never add acceptable-failure-rate hooks or mutate `session.exitstatus` to mask failures.
- Tests must be order-independent; do not assert absolute values of process-global counters unless the fixture resets them.
- Endpoint tests that do not test infrastructure should not require live PostgreSQL, Redis, Statsig, Unleash, Sentry, Logfire, or Datadog.
- For runtime regressions, add a regression test before or with the fix.

## Context discipline

Do not load large generic guidance files preemptively. Use repository code and focused docs as the source of truth. Specialized reusable procedures live under `.agents/skills/` and should be loaded only when relevant. Platform-specific rules should be path-scoped and must not duplicate this file.

For architecture or operational detail, inspect `README.md`, `docs/`, `pyproject.toml`, the relevant workflow, and the implementation being changed rather than expanding this file.