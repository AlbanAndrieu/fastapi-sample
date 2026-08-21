# Claude Code

Use `AGENTS.md` as the canonical repository guide.

## Minimal workflow

- Python 3.12 + FastAPI; ASGI app: `nabla.main:app`.
- Package manager: `uv`; never use Poetry/Pipenv instructions for this repository.
- Before push: `bash scripts/quality-gate.sh` and fix every failure.
- Unexpected Pytest failures must fail CI.
- For application wiring changes, run the FastAPI ASGI smoke test and a concrete route such as `/api` or `/health`.
- Do not initialize network clients, databases, telemetry exporters, Unleash, or Statsig during module import.
- Load `.agents/skills/*/SKILL.md` only when the task matches the skill description.
- Load detailed docs/rules only for the files or subsystem being changed.

Do not duplicate or override `AGENTS.md`; if prose documentation conflicts with executable tests/configuration, trust the executable source of truth.
