````instructions
# FastAPI Sample - AI Agent Instructions

## Architecture Overview

This is a **production-grade FastAPI application** with comprehensive observability, multi-database support, and enterprise integrations:

### Core Structure
- **Main application**: [nabla/main.py](nabla/main.py) - FastAPI app entry point with Datadog tracing, Sentry error tracking, Prometheus metrics, and Pyroscope profiling
- **Alternate entries**: [server_app.py](server_app.py) (uvicorn), [server_all.py](server_all.py) (gunicorn), [server_mcp.py](server_mcp.py) (FastMCP server)
- **API modules**: Modular routers in [nabla/api/](nabla/api/) - ping, v1, v2, users, notes, demo, auth, test
- **Database**: PostgreSQL via SQLAlchemy + Alembic migrations, psycopg3 connection pooling
- **Auth**: Keycloak OpenID Connect with JWT tokens ([nabla/api/auth/keycloak.py](nabla/api/auth/keycloak.py), [nabla/api/users/](nabla/api/users/))
- **Configuration**: Pydantic Settings pattern in [nabla/config_settings.py](nabla/config_settings.py) with `.env` file cascade
- **Integrations**: Temporal workflows ([nabla/temporalio/](nabla/temporalio/)), Redis pub/sub, DefectDojo security, Loki logging
- **Frontend**: Vue.js client in [vue-client/](vue-client/), Vite UI tooling

### Service Integrations
- **Observability**: Datadog (APM + profiling), Prometheus (metrics), Sentry (errors), Pyroscope (profiling)
- **Feature flags**: Unleash via GitLab + Statsig
- **Caching/messaging**: Redis for FastAPI-Cache and WebSocket pub/sub
- **Workflows**: Temporal for async task orchestration
- **Admin panel**: SQLAdmin for database management UI

## Development Workflow

### Environment Setup
```bash
# Python 3.12+ required
pyenv install 3.12.3 && pyenv local 3.12.3

# Poetry (primary) - install all dependencies
poetry install --all-extras
# Or specific groups: poetry install --with api,temporal,test,webui

# Pipenv (alternate) - full development setup
python -m pipenv install --dev --ignore-pipfile

# Enable direnv for automatic environment activation
direnv allow

# Install pre-commit hooks
pre-commit install
```

### Build & Run Commands (Makefile-driven)

**Development servers:**
```bash
make up-uvicorn        # Dev server with hot-reload (port 8091, 1 worker)
make up-gunicorn       # Production server (port 8091, N workers with uvicorn workers)
make up-python         # Direct Python execution via server_app module
make up-mcp            # FastMCP server (port 8000)
```

**Testing:**
```bash
make test              # Full test suite with pytest
make test-fastest      # Quick run with fail-fast (--exitfirst)
make test-continuous   # Watch mode using pytest-watcher
make test-debug-last   # Debug last failed test with pdb
```

**Code quality:**
```bash
make format            # Auto-format with ruff
make lint              # Lint checks with ruff
make pre-commit-test   # Run all pre-commit hooks
```

**Docker:**
```bash
make build-docker      # Build container image
make up-docker         # Run containerized app
make clean-docker      # Remove images and cleanup
```

**Documentation:**
```bash
make docs-serve        # Serve Sphinx docs on localhost:8000 (background)
make docs-publish      # Build and deploy to GitHub Pages
```

**Data science:**
```bash
make setup-jupyter-local  # Install Miniconda + Jupyter
make jupyter-local        # Launch Jupyter Lab
```

### Testing Conventions

**Key patterns from [tests/unit/conftest.py](tests/unit/conftest.py) and [pytest.ini](pytest.ini):**
- **Test client fixture**: `test_app` provides `TestClient` for all tests
- **Environment decorator**: `@requires_env("staging", "prod")` for conditional tests
- **Acceptable failure rate**: 50% threshold allows partial failures in CI
- **Async support**: `asyncio_mode = auto` handles async test functions automatically
- **Mock credentials**: All sensitive env vars mocked in `pytest.ini` env section
- **Random execution**: `--random-order` flag prevents test order dependencies
- **Markers**: `@pytest.mark.webtest` for integration tests, `@pytest.mark.skip()` for WIP

**Database testing:**
- Use `DB_URL_INIT` (sync SQLAlchemy) for test fixtures, not `DB_URL` (async)
- Tests use in-memory SQLite or separate test PostgreSQL instance

### Code Quality Standards

**Ruff (replaces Black, isort, flake8, pylint):**
```bash
ruff format .          # Format code (88 char line length)
ruff check . --fix     # Lint and auto-fix issues
```

**Type checking:**
- Pyright configured via [pyrightconfig.json](pyrightconfig.json)
- Use Python 3.12 type syntax: `Union[X, Y]` not `X | Y`, `Optional[X]` not `X | None`
- Always annotate function signatures, return types, and class attributes

**Pre-commit hooks:**
- Configured in `.pre-commit-config.yaml`
- Runs ruff, pyright, security scanners (bandit, trivy), yaml/json linters
- Update hooks: `make pre-commit-update`

## Key Patterns & Conventions

### Configuration Management

**Settings pattern** ([nabla/config_settings.py](nabla/config_settings.py)):
```python
# Settings cascade: environment vars → .env → .env.local → .env.secrets
class _Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", ".env.local"],
        env_nested_delimiter="__",  # REDIS__HOST → redis.host
    )

    # Always use Annotated with Field() for validation
    db_host: Annotated[str, Field(default="localhost", min_length=1)]
    api_key: Annotated[SecretStr, Field(min_length=8)]  # Use SecretStr for secrets

# Cached singleton pattern
@lru_cache()
def get_settings() -> APIDeploymentSettings:
    return APIDeploymentSettings()
```

**Environment variables:**
- Production URLs use Consul service discovery: `pg-gra.service.gra.dev.consul`
- Test/local values provided in [pytest.ini](pytest.ini) and `.env.local`
- Never log secrets (use `SecretStr.get_secret_value()` sparingly)

### Database Patterns

**Dual connection strategy** ([nabla/api/db/database.py](nabla/api/db/database.py)):
```python
# Async operations (FastAPI routes) - uses psycopg3
DB_URL = "postgresql+psycopg://user:pass@host:5432/db"
AsyncSessionLocal = async_sessionmaker(async_engine)

# Sync operations (Alembic, pytest fixtures) - uses psycopg2 or vanilla driver
DB_URL_INIT = URL.create(drivername="postgresql", ...)  # No +psycopg
SessionLocal = sessionmaker(engine)
```

**Connection pooling:**
- psycopg3 `ConnectionPool` with `min_size=0, max_size=1` (not SQLAlchemy pool)
- `NullPool` for SQLAlchemy to avoid double-pooling

**JSON optimization:**
```python
# Use orjson for 2-3x faster serialization
def orjson_serializer(obj):
    return orjson.dumps(obj, option=orjson.OPT_SERIALIZE_NUMPY).decode()

engine = create_engine(
    json_serializer=orjson_serializer,
    json_deserializer=orjson.loads,
)
```

**Migrations:**
```bash
alembic revision --autogenerate -m "Add user_role column"
alembic upgrade head
alembic downgrade -1
```

### API Design Patterns

**Response optimization:**
```python
from fastapi.responses import ORJSONResponse

# Use as default for 2-3x faster JSON serialization
app = FastAPI(default_response_class=ORJSONResponse)
```

**Rate limiting:**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.get("/api/resource")
@limiter.limit("5/minute")
async def get_resource():
    ...
```

**Feature flags:**
```python
# Unleash via GitLab
from nabla.config_settings import client

if client.is_enabled("new_feature"):
    # Feature logic
```

**Router organization:**
```python
# nabla/api/users/users.py
router = APIRouter(prefix="/users", tags=["users"])

# nabla/main.py
from nabla.api.users import users
app.include_router(users.router)
```

### Observability Patterns

**Datadog tracing** (must patch BEFORE imports):
```python
from ddtrace import patch, tracer, Profiler

# Start profiler immediately
prof = Profiler(env="prod", service="fastapi-sample")
prof.start()

# Patch integrations early
patch(sqlalchemy=True, redis=True, fastapi=True)

# Set user context
from ddtrace.contrib.trace_utils import set_user
set_user(tracer, user_id=user.id, email=user.email)
```

**Prometheus metrics:**
```python
# Custom middleware in nabla/utils/prometheus.py
from prometheus_client import Counter, Histogram

REQUESTS = Counter("http_requests_total", "Total requests")
REQUESTS_PROCESSING_TIME = Histogram("http_request_duration_seconds")

# Metrics endpoint automatically exposed at /metrics
```

**Structured logging:**
```python
# Use loguru (configured in nabla/utils/logger.py)
from nabla.utils.logger import logger

logger.info("User action", user_id=123, action="login")  # Structured context
logger.bind(request_id=req_id).info("Processing request")  # Bind context
```

**Error tracking:**
```python
# Sentry initialized in main.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

sentry_sdk.init(
    dsn=SENTRY_DSN,
    integrations=[FastApiIntegration()],
    traces_sample_rate=0.1,
)
```

### Python Code Style

**From [.cursor/rules/120_python.mdc](.cursor/rules/120_python.mdc):**
- Google-style docstrings for all public functions/classes
- Use `pathlib.Path` over `os.path` for file operations
- Type annotations required: function signatures, return types, class attributes
- Python 3.12 syntax: `Union[X, Y]` not `X | Y`, `Optional[X]` not `X | None`
- Prefer Pydantic models over dataclasses, TypedDict, NamedTuple for structured data
- Use loguru for logging (no print statements); rich for user-facing output
- Single-line comprehensions over iterative building; use `itertools`/`functools` to reduce nesting
- Settings/constants in [nabla/config_settings.py](nabla/config_settings.py), secrets in `.env.secrets`
- Private helpers prefixed with underscore (`_helper_function`)
- Use emojis in logs for visual recognition (🛢️ for DB, 🔥 for errors, ✅ for success)

**FastAPI specifics** ([.cursor/rules/700_fastapi.mdc](.cursor/rules/700_fastapi.mdc)):
- Type hints for all route parameters and return values
- Pydantic models for request/response validation
- Dependency injection for database sessions, auth, shared logic
- Background tasks for non-blocking operations: `BackgroundTasks.add_task()`
- Explicit status codes: 201 for creation, 404 for not found, 400 for validation errors
- APIRouter for feature-based organization

### Docker & Deployment

**Multi-stage Dockerfile:**
```dockerfile
# builder-base stage for dependency caching
FROM python:3.12-slim AS builder-base
RUN --mount=type=secret,id=CI_JOB_TOKEN \
    poetry install --no-dev

# Final stage
FROM python:3.12-slim
COPY --from=builder-base /app/.venv /app/.venv
```

**Build with secrets:**
```bash
docker build \
  --secret id=CI_JOB_TOKEN,env=CI_PIP_GITLABJUSMUNDI_TOKEN \
  --build-arg ENV=dev \
  -t registry.gitlab.com/AlbanAndrieu/fastapi-sample:1.2.3 \
  .
```

**docker-compose.yaml:**
- Loads `.env.local` and `.env.secrets` automatically
- Exposes port 8080 (mapped to internal 8080)
- Volume mounts current directory for development

## Common Pitfalls & Solutions

1. **Database URL confusion**
   - ❌ Using `DB_URL` (async psycopg) in Alembic migrations
   - ✅ Use `DB_URL_INIT` (sync) for migrations, `DB_URL` for FastAPI routes

2. **psycopg version mismatch**
   - ❌ Installing `psycopg2` or `psycopg2-binary`
   - ✅ Use `psycopg[binary,pool]` (psycopg3) exclusively

3. **Async session management**
   - ❌ Manual session commit/close or reusing sessions
   - ✅ Always use `async with AsyncSessionLocal() as session:` pattern

4. **Datadog tracing order**
   - ❌ Patching after importing SQLAlchemy or creating engines
   - ✅ Call `patch(sqlalchemy=True)` before any `create_engine()` calls

5. **Environment variable naming**
   - ❌ Hardcoding service URLs like `localhost:5432`
   - ✅ Use Consul discovery: `pg-gra.service.gra.dev.consul` or env vars

6. **Pydantic Field validation**
   - ❌ `enable_metrics: bool = Annotated[bool, Field(default="localhost")]`  # Wrong type
   - ✅ `enable_metrics: Annotated[bool, Field(default=False)]`

7. **Secret logging**
   - ❌ Logging `SecretStr` directly: `logger.info(f"Pass: {settings.password}")`
   - ✅ Never log secrets; use `.get_secret_value()` only when necessary

## Project-Specific Commands

**Database operations:**
```bash
# Run migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "Description"

# Check current revision
alembic current
```

**Health checks:**
```bash
curl http://localhost:8091/health      # Application health
curl http://localhost:8091/metrics     # Prometheus metrics
curl http://localhost:8091/v1/ping     # API v1 liveness
curl http://localhost:8091/v2/ping     # API v2 liveness
```

**Redis (required for caching/websockets):**
```bash
sudo service redis-server start
redis-cli -h localhost -p 6379 ping    # Should return PONG
```

**Vue.js frontend:**
```bash
cd vue-client/
npm install
npm run dev           # Development server
npm run build         # Production build
```

**Jupyter notebooks:**
```bash
make setup-jupyter-local    # One-time setup (installs Miniconda)
make jupyter-local          # Launch Jupyter Lab
```

## Repository Context

- **Languages**: Python 3.12+ (backend), TypeScript/Vue.js (frontend), Go (experiments)
- **Build tools**: Poetry/pipenv (Python), npm (JS), Makefile (orchestration)
- **Infrastructure**: Nomad job specs ([job.nomad](job.nomad)), Nix flakes ([flake.nix](flake.nix)), devenv ([devenv.nix](devenv.nix))
- **CI/CD**: GitHub Actions (`.github/workflows/`), GitLab CI (`.gitlab-ci.yml` if present)
- **Documentation**: Sphinx in [docs/source/](docs/source/), served via `make docs-serve`
- **Notebooks**: Training examples in [notebooks/training_example.ipynb](notebooks/training_example.ipynb)
- **Security**: Trivy SBOM ([trivy-sbom.json](trivy-sbom.json)), Datadog static analysis, pre-commit hooks

## Adding New Features

**New API endpoint:**
1. Create router in `nabla/api/<feature>/` directory
2. Define Pydantic models in `models.py`
3. Implement route handlers with type annotations and docstrings
4. Register router in [nabla/main.py](nabla/main.py): `app.include_router(feature.router)`
5. Add tests in `tests/unit/test_<feature>.py`

**New database model:**
1. Add SQLAlchemy model to `nabla/api/<feature>/models.py`
2. Generate migration: `alembic revision --autogenerate -m "Add feature table"`
3. Review and edit migration in `alembic/versions/`
4. Apply migration: `alembic upgrade head`

**New dependency:**
1. Add to appropriate `[tool.poetry.group.<group>]` in [pyproject.toml](pyproject.toml)
2. Run `poetry lock` to update lockfile
3. Install: `poetry install --with <group>`

**Code quality checklist:**
1. Run `make format` to auto-format code
2. Run `make lint` to check for issues
3. Run `make test` to verify tests pass
4. Commit with conventional commit message: `feat:`, `fix:`, `docs:`, etc.
5. Pre-commit hooks will run automatically

## Additional Instructions

**For documentation changes** (see [.github/instructions/documentation.instructions.md](.github/instructions/documentation.instructions.md)):
- Use present tense verbs ("is", "open") instead of past tense
- Write in second person ("you") for direct address
- Use active voice where subject performs action
- Include code examples and links to related resources

**For Terraform changes** (see [.github/instructions/terraform.instructions.md](.github/instructions/terraform.instructions.md)):
- Use latest stable provider versions
- Store secrets in HashiCorp Vault or AWS Secrets Manager
- Mark sensitive variables with `sensitive = true`
- Follow principle of least privilege for IAM roles
- Use separate projects for major infrastructure components

---
applyTo: "**"
---
# Project general coding standards

## Naming Conventions
- Use PascalCase for component names, interfaces, and type aliases
- Use camelCase for variables, functions, and methods
- Prefix private class members with underscore (_)
- Use ALL_CAPS for constants

## Error Handling
- Use try/catch blocks for async operations
- Implement proper error boundaries in Vue components
- Always log errors with contextual information

````
