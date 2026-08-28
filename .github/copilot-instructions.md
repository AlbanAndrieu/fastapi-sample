# FastAPI Sample — GitHub Copilot instructions

Follow `AGENTS.md` as the repository-wide engineering, security, validation, publication, maintainability, and tool/context-efficiency policy. Do not duplicate those rules here.

Use current repository sources instead of historical architecture snapshots or command examples. In particular, derive behavior from `pyproject.toml`, `Makefile`, `nabla/`, `tests/`, `scripts/`, `.github/workflows/`, and the relevant documentation before making a change.

Task-specific files in `.github/instructions/` are intentionally scoped by path and should apply only when their declared file scope matches the work. Skills under `.agents/skills/` are on-demand: load only the skill required by the current task rather than preloading the skill tree.

For repository exploration, connector/MCP discovery, CI logs, deployment evidence and observability results, follow the progressive, targeted collection rules in `AGENTS.md`. First-class tools remain fully available whenever they are needed; context optimization must never reduce test coverage, security checks, diagnostics, or deployment validation.
