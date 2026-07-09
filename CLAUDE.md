# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Overview

**fastapi-sample** is a production-grade FastAPI application with comprehensive observability, multi-database support, enterprise integrations, and a modern Vue.js frontend. It also features extensive DevOps, data science, and CI/CD tooling.

### Core Architecture

- **Backend:** Python 3.12+, FastAPI app (`nabla/main.py`). Entry points include `server_app.py`, `server_all.py`, and `server_mcp.py`.
- **API Routers:** Modular structure under `nabla/api/`, supporting layered endpoints, JWT authentication (Keycloak), and feature modules (users, notes, test, etc).
- **Database:** PostgreSQL via SQLAlchemy (async/sync split) and Alembic migrations. Psycopg3 with connection pooling and in-memory SQLite for testing.
- **Configuration:** Pydantic Settings pattern (`nabla/config_settings.py`), environment variable cascade (.env, .env.local, .env.secrets).
- **Integrations:** Temporal workflows, Redis (cache/websockets), DefectDojo, Loki, Datadog, Prometheus, Sentry.
- **Frontend:** Vue.js client (`vue-client/`), Vite tooling.
- **DevOps/Data Science:** Jupyter, Sphinx docs, Makefile orchestration, multi-stage Dockerfile.

### Service Integrations

- **Observability:** Datadog, Prometheus, Sentry, Pyroscope.
- **Feature Flags:** Unleash via GitLab, Statsig.
- **Admin UI:** SQLAdmin.
- **CI/CD:** GitHub Actions (`.github/workflows/`), GitLab CI (`.gitlab-ci.yml`).

---

## Common Commands & Development Tasks

### Environment Setup

```bash
pyenv install 3.12.3 && pyenv local 3.12.3
uv sync                                 # Install dependencies (default)
uv run <command>                        # Run CLI tools in project venv
# To ensure strict lockfile: uv sync --frozen
direnv allow                           # Enable direnv
pre-commit install                     # Install hooks
```

### Build & Run (via Makefile)

```bash
make up-uvicorn        # Dev server with reload (port 8091)
make up-gunicorn       # Production server (port 8091)
make up-python         # Direct Python execution
make up-mcp            # FastMCP server (port 8000)
```

### Testing

```bash
make test              # Full pytest suite
make test-fastest      # Quick run (fail-fast)
make test-continuous   # Watch mode (pytest-watcher)
make test-debug-last   # Debug last failed test
```

- **Run a single test:**  
  `pytest tests/path/to/test_file.py::TestClass::test_method`
- **Test collection only:**  
  `.venv/bin/pytest tests --collect-only`

### Code Quality

```bash
make format            # Auto-format via ruff
make lint              # Lint checks via ruff
make pre-commit-test   # Run all pre-commit hooks
ruff format .          # Format code
ruff check . --fix     # Lint + autofix
pyright --outputjson   # Static type checks
python -m flake8 nabla --max-line-length=88 --max-complexity=30
```

### Docker

```bash
make build-docker      # Build container image
make up-docker         # Run containerized app
make clean-docker      # Remove images and cleanup
```

### Documentation

```bash
make docs-serve        # Serve Sphinx docs (localhost:8000)
make docs-publish      # Deploy GitHub Pages
```

### Data Science

```bash
make setup-jupyter-local  # Install Miniconda + Jupyter
make jupyter-local        # Launch Jupyter Lab
```

---

## High-Level Design Patterns & Conventions

### Configuration

- Uses Pydantic settings cascade: environment -> .env -> .env.local -> .env.secrets.
- Sensitive settings via `SecretStr`. Never log secrets.
- Use Consul for URLs in production, `.env.local` for test/dev.

### Database

- Async/session split for FastAPI vs Alembic tests, use correct URL.
- Connection pooling via psycopg3.
- Migrations with Alembic:
  ```bash
  alembic upgrade head
  alembic revision --autogenerate -m "Describe migration"
  ```

### API

- All routers organized by feature directory, registered in main app.
- Use Pydantic models for validation, type-annotate parameters and returns.
- Dependency injection for DB, auth, background tasks.
- Rate limiting with `slowapi`.
- Feature flags with Unleash client.

### Observability & Logging

- Datadog tracing (patch before imports).
- Prometheus endpoints at `/metrics`.
- Structured logging via loguru.
- Sentry integration for error tracking.

### Code Style (Python/Cursor/Copilot)

- Google-style docstrings.
- Type annotations (function, return, class attributes).
- Prefer `pathlib.Path` over `os.path`.
- Pydantic for structured data.
- Loguru (no print), rich for output.
- Comprehensions, `itertools`, `functools` for clarity.
- Settings in `config_settings.py`, secrets in `.env.secrets`.
- Emojis in logs for context.

#### FastAPI-specific

- Type hints required on all endpoints.
- Dependency injection for shared services.
- Background tasks for async ops.
- Explicit status codes.
- Use `APIRouter` for organization.

### Docker & Deployment

- Multi-stage build: dependency caching, secrets via build args.
- Compose auto-loads `.env.local` and `.env.secrets`.
- Mounted volumes for dev; port mapping.

---

## Project-Specific Linting & Test Hooks

- **Pre-commit**: Ruff, Pyright, Bandit, Trivy, yaml/json linters.
- **Update pre-commit hooks**:  
  `make pre-commit-update`
- **CI/CD**: GitHub Actions, GitLab CI, comprehensive test execution and code quality reporting.

---

## Common Pitfalls & Solutions

1. **Database URL Mismatch:** Use sync URL for Alembic, async for FastAPI endpoints.
2. **psycopg version:** Only use psycopg3.
3. **Async Sessions:** Always use context manager (`async with`).
4. **Datadog Order:** Patch integrations before creating engine.
5. **Secrets:** Never log secret values.
6. **Field validation:** Annotate fields with correct types.

---

## Adding Features/Endpoints

- New API: create router in `nabla/api/<feature>`, add models, implement handlers, test, register router.
- New DB model: add to `models.py`, generate Alembic migration, review/edit, apply.
- New dependency: add to group in `pyproject.toml`, `poetry lock`, install.

---

## General Coding Standards

- **Naming:** PascalCase for components, camelCase for variables/functions, underscores for private members, ALL_CAPS for constants.
- **Errors:** Use try/catch in async, log with context, Vue error boundaries.

---

## References

- See README.md for detailed init, requirements, additional context.
- See `.pre-commit-config.yaml` for hook/CI configuration.
- See `.github/copilot-instructions.md` for coding standards and error handling.
- For documentation or Terraform, refer to specialized instructions in `.github/instructions/`.

---

**This CLAUDE.md streamlines future Claude Code sessions: follow the command conventions, respect settings/database patterns, and adhere to project-specific coding and architectural guidance for confident productivity.**

---

If you need further architectural details or specific commands, refer to the README.md and pyproject.toml for the latest updates.
