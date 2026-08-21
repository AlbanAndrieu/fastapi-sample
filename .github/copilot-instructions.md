# GitHub Copilot repository instructions

`AGENTS.md` is the canonical repository guide. Keep this file as a small Copilot adapter.

- Python 3.12, FastAPI, `uv`; ASGI app is `nabla.main:app`.
- Use `[project].dependencies` for anything required by the minimal production runtime. Dependency groups are additive profiles.
- Never tolerate unexpected test failures. Do not add acceptable-failure thresholds.
- Tests must be order-independent and unit tests must not require PostgreSQL, Redis, feature-flag services, or other external systems unless explicitly marked integration tests.
- For changes to middleware, routes, mounts, MCP wiring, or lifespan, validate a real ASGI request with `TestClient`.
- Avoid network/client initialization at module import time; use lazy factories or FastAPI lifespan.
- Before push run `bash scripts/quality-gate.sh`. Never bypass hooks or weaken lint/security checks merely to make CI pass.
- Use safe Ruff fixes by default. Prefer Python 3.12 native typing (`X | None`, `list[str]`).
- Load `.github/instructions/*.instructions.md` only when their `applyTo` scope matches the files being edited.
- Load `.agents/skills/*/SKILL.md` only when the task matches that skill.

If this file conflicts with `AGENTS.md`, tests, `pyproject.toml`, or workflow configuration, those sources take precedence.
