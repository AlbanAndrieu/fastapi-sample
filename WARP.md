# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

FastAPI-based sample application with real-time sensor monitoring, authentication, database integrations, and comprehensive observability. This is a production-grade FastAPI application designed for the JusMundi organization, featuring JWT authentication via Keycloak, PostgreSQL persistence, Redis for caching/WebSockets, and full monitoring with Datadog, Sentry, and Prometheus.

## Common Commands

### Development

```bash
# Setup environment
direnv allow
pyenv install 3.12.3
pyenv local 3.12.3
python -m pipenv install --dev --ignore-pipfile
pre-commit install

# Alternative: Poetry installation
poetry install --with format,test,extra,open_telemetry,api,deployment,influxdb,panda,temporal,utils,webui

# Run the application
make up-uvicorn              # Uvicorn server on port 8091
make up-gunicorn             # Gunicorn with workers (recommended for production)
make up-python               # Basic Python server
make up-mcp                  # MCP server on port 8000

# Direct commands
.venv/bin/uvicorn server:app --reload --workers 1 --host 0.0.0.0 --port 8091
DEBUG=1 uv run uvicorn serve:app --reload --workers 1 --host 0.0.0.0 --port 8091
```

### Testing

```bash
# Run tests
pytest --cov=nabla --cov-report term --cov-report xml:coverage.xml --junitxml pytest-junit.xml --no-ddtrace --no-cov

# Run specific test
pytest tests/path/to/test_file.py::test_function_name

# Test with tox
tox py312                    # Python 3.12 tests
make test-tox                # Run tox tests
make test-nox                # Run nox tests
```

### Linting & Formatting

```bash
# Ruff (primary linter/formatter)
ruff check --output-format gitlab > report_ruff.json
ruff format --check
ruff format                  # Auto-format
make ruff                    # Run all linting

# Flake8
python -m flake8 nabla --max-line-length=88 --max-complexity=30

# Type checking
pyright --outputjson > report_raw.json
pyright-to-gitlab-ci --src report_raw.json --output report_pyright.json --base_path .
```

### Database

```bash
# Alembic migrations
alembic upgrade head         # Apply migrations
alembic downgrade -1         # Rollback one migration

# Connect to database
psql -h pg-gra.service.gra.dev.consul -U postgres
```

### Docker

```bash
# Build
make build-docker            # Build Docker image
make build-buildah           # Build with buildah

# Run
make up-docker               # Run container
make debug                   # Enter container for debugging

# Testing
make test-dive               # Analyze image layers
make test-cst                # Container structure tests
make sast-docker             # Security scan with Trivy
```

## Architecture Overview

### Application Structure

- **`main.py`**: Main entry point that imports the FastAPI app from `nabla.main`
- **`server.py`**: Uvicorn server configuration with Pyroscope profiling
- **`nabla/`**: Main application package
  - **`main.py`**: Core FastAPI application setup, middleware, lifespan management
  - **`config_settings.py`**: Centralized configuration using Pydantic settings
  - **`api/`**: API endpoints organized by domain
    - `ping.py`: Health check endpoints
    - `v1.py`, `v2.py`: Versioned API routes
    - `auth/keycloak.py`: JWT authentication via Keycloak
    - `users/`: User management with fastapi-users
    - `notes/`: Notes CRUD operations
    - `demo/`: Demo endpoints including sensor data, integrations
    - `db/`: Database configuration and models
  - **`utils/`**: Shared utilities
    - `log_config.py`: Structured logging setup
    - `prometheus.py`: Prometheus metrics

### Technology Stack

**Core:**

- FastAPI 0.115.3+ with async/await
- Python 3.12+
- Poetry & Pipenv for dependencies
- Pydantic for validation and settings

**Database:**

- PostgreSQL (asyncpg, databases, SQLAlchemy 2.0, SQLModel)
- Alembic for migrations
- Redis for caching and pub/sub

**Authentication:**

- Keycloak (python-keycloak)
- JWT tokens (PyJWT)
- fastapi-users for user management

**Observability:**

- Datadog (ddtrace) for APM
- Sentry for error tracking
- Prometheus for metrics
- Pyroscope for profiling
- OpenTelemetry support
- Logfire for structured logging

**API Features:**

- WebSockets (SSE via sse-starlette)
- Rate limiting (SlowAPI)
- Circuit breakers (pybreaker)
- Caching (fastapi-cache2)
- Feature flags (fastapi-featureflags, UnleashClient)

### Key Patterns

**1. Dependency Injection**: FastAPI's dependency system is used throughout for database sessions, authentication, and configuration.

**2. Async-First**: All database and I/O operations use async/await. Database queries use `databases` library or SQLAlchemy async sessions.

**3. Lifespan Management**: Application startup/shutdown handled via `@asynccontextmanager` in `main.py`:

- Initializes FastAPICache, Redis, database connections
- Starts background tasks (system metrics, event listeners)
- Properly cleans up on shutdown

**4. Authentication Flow**:

- JWT tokens issued by Keycloak
- Public keys fetched from Keycloak for validation
- Middleware validates tokens on protected routes
- User context tracked via Datadog `set_user()`

**5. Configuration Management**:

- Environment variables via Pydantic BaseSettings
- `.env` files supported
- Separate configs for dev/staging/production
- Database URLs, API keys, feature flags centralized in `config_settings.py`

**6. Error Handling**:

- Global exception handlers in FastAPI app
- Structured logging with context
- Sentry integration for production errors
- Circuit breakers for external service calls

**7. Testing Strategy**:

- pytest with async support (pytest-asyncio)
- Test database fixtures
- Mock external services (Keycloak, Datadog)
- Pre-commit hooks validate tests before commit

## Development Workflow

### Adding a New Endpoint

1. Create route in appropriate `nabla/api/` subdirectory (e.g., `nabla/api/myfeature/routes.py`)
2. Define Pydantic models for request/response
3. Add database models if needed (use SQLModel)
4. Create Alembic migration if schema changes: `alembic revision --autogenerate -m "description"`
5. Register router in `nabla/main.py`
6. Add tests in `tests/`
7. Run linting before commit: `ruff check` and `ruff format`

### Database Changes

1. Modify SQLModel models in `nabla/api/*/models.py`
2. Generate migration: `alembic revision --autogenerate -m "add_field_to_table"`
3. Review migration in `alembic/versions/`
4. Apply: `alembic upgrade head`
5. Test rollback: `alembic downgrade -1` then re-upgrade

### Authentication

Protected endpoints use FastAPI dependencies:

```python
from nabla.api.auth.keycloak import get_current_user

@router.get("/protected")
async def protected_route(user = Depends(get_current_user)):
    # user is validated JWT payload
```

JWT tokens must be passed as `Authorization: Bearer <token>` header.

### Environment Variables

Key variables (see `nabla/config_settings.py` for full list):

- `DB_URL`: PostgreSQL connection string
- `REDIS_HOST`, `REDIS_PORT`: Redis connection
- `KEYCLOAK_*`: Keycloak configuration
- `DD_*`: Datadog settings
- `SENTRY_DSN`: Sentry error tracking
- `OTEL_*`: OpenTelemetry configuration
- `UNLEASH_*`: Feature flags

Never commit secrets. Use `.env` file locally and environment variables in deployment.

## Important Files

- **`pyproject.toml`**: Dependencies, tool configurations (Ruff, pytest, mypy, Black)
- **`.pre-commit-config.yaml`**: Pre-commit hooks for linting, formatting, security
- **`Makefile`**: Common development tasks
- **`Dockerfile`**: Container build instructions
- **`alembic/`**: Database migrations
- **`tests/`**: Test suite
- **`.cursor/rules/`**: Cursor IDE rules (also relevant for understanding project conventions)

## Code Style

- **Line length**: 88 characters (Black/Ruff default)
- **Type hints**: Required for public APIs, encouraged everywhere
- **Docstrings**: Google style
- **Imports**: Sorted with Ruff (isort)
- **Async**: Use `async/await` for I/O operations
- **Testing**: pytest with async support
- **Error handling**: Structured logging, avoid bare `except:`

From `.cursor/rules/001_project-description.mdc`:

- Add typing wherever possible
- Add trailing commas
- Avoid generic variable name `df` for dataframes
- Prefer `Path.open()` over `open()`

## Important Notes

### Deployment

- Application expects to run behind Traefik/HAProxy with JWT validation by KrakenD
- Health checks available at `/health` and `/ping`
- Metrics exposed at `/metrics` (Prometheus format)
- OpenAPI docs at `/docs`

### Database

- Connection pool managed by `databases` library
- Use async context managers for transactions
- Database URL should use `asyncpg` driver for PostgreSQL
- Test database should be separate from dev/prod

### Monitoring

- Datadog profiler starts on import (prof.start() in `main.py`)
- Traces filtered to exclude noisy endpoints (see `FilterbyName` class)
- Custom Prometheus metrics in `nabla/utils/prometheus.py`
- Structured logs via `structlog` and `python-json-logger`

### Redis

- Used for caching (fastapi-cache2) and WebSocket pub/sub
- Connection managed in lifespan
- Falls back gracefully if unavailable (circuit breaker pattern)

### CI/CD

- GitLab CI configured (`.gitlab-ci.yml`)
- Pre-commit hooks enforce quality gates
- Docker images pushed to GitLab Container Registry
- Trivy scans for vulnerabilities

## Gotchas

- **Alembic + asyncpg**: Alembic requires synchronous database URL. Use `postgresql://` not `postgresql+asyncpg://` in DB_URL for Alembic operations only.
- **JWT expiration**: Tokens expire and need refresh. Implement token refresh logic in clients.
- **Circuit breakers**: External service calls fail open after 2 consecutive errors for 10 seconds.
- **Pre-commit hooks**: Can be slow. Use `SKIP=hook_name git commit` to bypass specific hooks during development (not recommended for final commits).
- **Poetry vs Pipenv**: Both are supported. Poetry is preferred for new installations. See `pyproject.toml` for Poetry groups.
