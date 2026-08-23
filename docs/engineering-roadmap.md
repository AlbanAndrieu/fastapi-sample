# Engineering and security roadmap

This document is the single planning source for future `fastapi-sample` pull
requests. Keep completed work, open follow-ups and intentional compatibility
exceptions here rather than creating additional TODO or refactoring documents.

## Operating constraints

- Keep Python 3.13 and `uv` consistent across local development, CI, Docker and
  FastAPI Cloud.
- Preserve existing public endpoint behavior until an identity provider is ready.
- Stage Keycloak/OIDC integration with the homelab deployment tracked in
  [nabla-compose#33](https://github.com/AlbanAndrieu/nabla-compose/pull/33).
  That pull request does not yet provide Keycloak; authentication remains a
  follow-up.
- Keep the existing size policy: warn above 400 Python lines and fail above
  700 lines, with explicit generated-code and migration exceptions.
- Grandfather oversized modules already present on `main` until they can be
  split without losing recently integrated functionality.
- Configure GitHub branch protection only after the application and CI changes
  are stable; do not change `main` protection in the current implementation.

## P0 — Credentials and private data

- [ ] Rotate PostgreSQL credentials if historical application logs contain them.
- [ ] Audit retained FastAPI Cloud, Sentry, Logfire and centralized logs for
  connection strings, reset tokens, verification tokens and other credentials.
- [ ] Assess whether historical GitHub commits containing private contact data
  require history cleanup or repository-specific secret/privacy remediation.
- [x] Stop logging PostgreSQL credentials and complete connection strings.
- [x] Recognize short `pass=` and `pass:` labels in structured-log redaction.
- [x] Stop writing password-reset and account-verification tokens to logs.
- [x] Keep private telephone numbers and precise home addresses out of public
  profile source files, tests and API/MCP responses.
- [x] Use a dedicated public profile response model that never includes a
  password.

## P1 — Progressive endpoint protection

- [x] Keep SQLAdmin and operational routes usable until an identity provider is
  deployed.
- [x] Allow an optional `ADMIN_ACCESS_KEY` for `/admin` and its descendants.
- [x] Allow an optional `DIAGNOSTICS_ACCESS_KEY` for detailed health, homelab,
  metrics and Sentry diagnostic endpoints while leaving `/health` public.
- [x] Preserve optional `MCP_OPS_KEY` compatibility and compare configured keys
  in constant time.
- [x] Provide `MCP_OPS_REQUIRE_KEY=true` for operators who explicitly want
  missing MCP credentials to fail closed.
- [x] Allow `ADMIN_ENABLED=false` without changing the current enabled default.
- [ ] Replace shared operational keys with Keycloak/OIDC authentication and
  explicit administration, diagnostics and MCP authorization scopes.
- [ ] Add Cloudflare Access, reverse-proxy restrictions or private networking for
  management endpoints once the desired access flow is defined.
- [ ] Publish a dedicated public homelab projection that excludes internal host
  names, ports and infrastructure details without breaking existing dashboards.
- [ ] Add rate limits and response caching to expensive dependency probes.

## P1 — Release and production deployment

- [ ] Trigger FastAPI Cloud deployment for the existing
  `semantic-release-published` repository dispatch.
- [ ] Check out the immutable release tag in validation and deployment jobs.
- [ ] Verify the deployed release version through the public version endpoint.
- [ ] Investigate why existing `feat:` commits did not advance version `1.4.1`;
  inspect semantic-release permissions, GitHub App credentials and workflow logs.
- [ ] Consolidate push and release-triggered deployment into a single production
  rollout after observing the repaired release sequence.
- [ ] Publish container images with both semantic-version and commit-SHA tags,
  signed provenance and generated SBOM artifacts.

## P1 — Observability and memory

- [x] Normalize Prometheus labels to route templates instead of raw request
  paths.
- [x] Group unmatched request paths into one bounded-cardinality label.
- [x] Respect `METRICS_ENABLED=false` for request instrumentation and periodic
  system-metric collection.
- [x] Keep Sentry logs and traces enabled when a Logfire token exists but
  `LOGFIRE_ENABLED=false`.
- [x] Disable external Sentry/Logfire exporters by default during pytest runs.
- [ ] Benchmark resident memory and startup time with Logfire, Redis,
  OpenTelemetry, Datadog and Prometheus independently enabled.
- [ ] Remove duplicated instrumentation and make expensive system-metric
  collection explicitly configurable.
- [ ] Add bounded-memory and high-cardinality regression tests.

## P1 — Continuous integration and repository governance

- [x] Use GitHub-compatible `CODEOWNERS` syntax with a real repository owner.
- [x] Run CodeQL against pull requests targeting `main`.
- [x] Make high-confidence, high-severity Bandit findings block Python CI.
- [x] Remove the unused Wrangler npm package, its worker-only scripts and
  orphaned transitive dependencies from the npm lockfile.
- [x] Keep the inverse `/sickz` certificate exception narrowly justified for
  both Ruff and Bandit instead of disabling TLS findings globally.
- [ ] Consolidate duplicate Pylint jobs and keep one authoritative Python
  quality gate.
- [ ] Make relevant Trivy findings blocking once the current vulnerability
  baseline has been triaged.
- [ ] Pin every reusable GitHub Action to a verified immutable commit SHA.
- [ ] Protect `main`, require reviewed pull requests and enforce the final
  mandatory test/security checks after the current refactoring stabilizes.

## P2 — Runtime and database architecture

- [x] Avoid opening the auxiliary PostgreSQL connection pool during module
  import.
- [ ] Consolidate SQLAlchemy, `databases` and psycopg pools behind one explicit
  application lifecycle.
- [ ] Move schema creation out of worker startup and run Alembic migrations as
  an explicit deployment step.
- [ ] Split installation groups into `runtime`, `observability`, `homelab`,
  `ai` and `dev`, then update the lockfile and test each supported deployment.
- [ ] Replace the Git-tagged TrueNAS dependency with an immutable commit or a
  maintained release package.
- [x] Align Docker's `uv` version with GitHub Actions.
- [x] Reduce `nabla/main.py` below 700 lines by extracting request middleware
  and Sentry initialization without removing current routers or integrations.
- [ ] Reduce production image size after runtime dependency groups are isolated.
- [ ] Make Debian package pinning reproducible without depending on package
  versions disappearing from the active repository.

## P2 — Local development and documentation

- [x] Make Docker Compose use the real `server_all:app` entrypoint and port 8080.
- [x] Bind local PostgreSQL and Redis ports to loopback by default.
- [x] Remove the notebook container's access to the host SSH directory.
- [ ] Merge the two Compose files into one documented configuration with
  optional development, notebook and observability profiles.
- [ ] Replace legacy Pipenv/Poetry instructions with a Python 3.13 + `uv`
  quickstart and archive obsolete Dockerfiles.
- [ ] Deduplicate Cursor, Codex, OpenCode and Copilot instructions while keeping
  `AGENTS.md` as the concise shared policy.
- [ ] Store generated SBOM reports as CI artifacts instead of tracking large
  generated files.
- [ ] Continue the MCP SDK integration review:
  <https://github.com/modelcontextprotocol/python-sdk>.

## Suggested future pull requests

1. `feat(security): introduce Keycloak-backed administrative access`
2. `feat(homelab): separate public and authenticated service projections`
3. `fix(release): complete immutable release-to-production orchestration`
4. `refactor(database): consolidate pools and deployment migrations`
5. `refactor(dependencies): isolate lean runtime and optional integrations`
6. `ci(security): enforce branch protection and mandatory security checks`
7. `docs(dev): standardize uv onboarding and shared agent instructions`

## Consolidated quality and refactoring backlog

The remaining sections preserve the quality roadmap introduced separately on
`main`. Keep this file as the only planning source for future pull requests.

### Quality baseline and future work


The following improvements have already been implemented:

- Ruff lint and formatting pass on `nabla/` and `tests/`.
- The active FastAPI, settings, Redis, Notes, and RAG modules pass targeted
  Pyright checks.
- Unit tests are separated from tests that require the full application or
  external services.
- Unit test baseline: **55 passed, 1 skipped, 42 deselected**.
- External observability and feature-flag clients are opt-in during tests.
- Redis, Statsig, Unleash, RAG watchers, and observability integrations no
  longer perform unnecessary network operations during ordinary imports.
- RAG embedding responses are validated for shape, count, numeric values, and
  consistent dimensions.
- Notes persistence returns generated IDs, closes sessions, rolls back on
  failure, and uses the correct note ID during updates.

Run the current baseline with:

```bash
ruff format --check nabla tests
ruff check nabla tests
pyright \
  nabla/main.py \
  nabla/config_settings.py \
  nabla/api/demo/socket/redis.py \
  nabla/api/notes/notes.py \
  nabla/api/notes/crud.py \
  nabla/api/notes/models.py \
  nabla/api/rag.py \
  nabla/rag/ingest.py
pytest tests/unit
python -m compileall -q nabla tests
git diff --check
```

### Priority 1: application factory and import safety

#### Work

- Introduce `create_app(settings)` instead of constructing the application at
  module import time.
- Move router registration into a dedicated function or module.
- Move middleware and observability configuration out of `nabla/main.py`.
- Move MCP and A2A mounting into explicit application setup functions.
- Ensure importing an API model, router, or test helper does not create pools,
  threads, SDK clients, tracers, or network requests.
- Replace the remaining global database and Redis clients with resources owned
  by `app.state` or injected dependencies.

#### Acceptance criteria

- A unit test can create a minimal application without PostgreSQL, Redis,
  Statsig, Unleash, Datadog, Sentry, MCP, or RAG.
- `python -c "import nabla.main"` performs no external network request.
- Two application instances can be created in one process without duplicate
  middleware, routes, metrics, or background tasks.

### Priority 2: lifecycle resilience

#### Work

- Use `contextlib.AsyncExitStack` to manage startup resources.
- Close Redis explicitly during shutdown.
- Ensure partially completed startup is rolled back when a later dependency
  fails.
- Add names and structured error reporting to background tasks.
- Decide whether a background-task crash should stop the application or be
  restarted with bounded backoff.
- Add startup and shutdown tests for success, partial failure, and cancellation.

#### Acceptance criteria

- Every acquired resource is released after normal shutdown and failed startup.
- No watcher, thread, pool, task, or client remains alive after lifecycle tests.
- Shutdown completes within a documented timeout.

### Priority 3: integration tests

#### Work

- Migrate the remaining `TestClient` suites to `httpx.AsyncClient` and
  `ASGITransport` where appropriate.
- Provide containerized PostgreSQL and Redis fixtures for tests marked
  `integration`.
- Run web rendering tests separately with `pytest -m webtest`.
- Remove environment-dependent skips where a deterministic fake or container
  can be used.
- Add a CI job for `pytest -m integration`.
- Keep unit tests network-disabled by default.

#### Acceptance criteria

- `pytest tests/unit` requires no external service and remains deterministic.
- `pytest -m integration` either provisions its dependencies or fails with a
  clear prerequisite message.
- Tests never silently convert failures into successful exit codes.

### Priority 4: Datadog and observability isolation

### Current issue

Importing the full application still loads Datadog and produces a Python 3.12
`crypt` deprecation warning. During pytest shutdown, the tracer can also log to
an already closed output stream.

#### Work

- Load Datadog modules only when `DD_TRACE_ENABLED=true`.
- Remove unconditional tracer configuration and user assignment.
- Make profiling, tracing, and PII collection independently configurable.
- Reconsider Sentry `send_default_pii=True` and sampling rates of `1.0`.
- Verify that disabled observability creates no threads or shutdown hooks.

#### Acceptance criteria

- Unit tests finish without Datadog warnings, five-second tracer waits, or
  logging errors.
- Disabled observability has no measurable import-time side effect.
- Production configuration documents sampling and PII choices explicitly.

### Priority 5: Notes domain cleanup

#### Work

- Replace legacy SQLAlchemy declarative models and `databases.Record` with one
  consistent SQLAlchemy 2 or SQLModel data-access approach.
- Change `Note.completed` from a string column to a boolean column through an
  Alembic migration.
- Store `created_date` as a timezone-aware timestamp and serialize it only at
  the API boundary.
- Remove the synchronous DB session work from async request handlers or execute
  it through a properly managed async session.
- Add response models for create, update, read, and delete operations.
- Decide whether updating a note must enqueue Redis work; expose queue failures
  with an intentional transaction policy.

#### Acceptance criteria

- Database and API types agree for IDs, booleans, and timestamps.
- Notes CRUD has unit and integration coverage for success, validation,
  rollback, missing records, and queue failures.
- No synchronous database call blocks the event loop.

### Priority 6: RAG architecture

#### Work

- Replace the mutable global `VECTOR_DB` with a `VectorStore` protocol.
- Provide an in-memory implementation for tests and a persistent implementation
  for production.
- Protect ingestion and search from concurrent mutation.
- Avoid duplicate ingestion when files change or the application restarts.
- Validate embedding model and vector dimensions against stored vectors.
- Add bounded concurrency, timeouts, and structured errors around embeddings.
- Move document parsing dependencies behind optional integration boundaries.

#### Acceptance criteria

- Search is deterministic under concurrent ingestion.
- Restarting the application does not duplicate existing chunks.
- Provider failures return a controlled API error rather than leaking raw
  exceptions.

### Priority 7: outbound HTTP and health checks

#### Work

- Create shared lifespan-owned `httpx.AsyncClient` instances.
- Define consistent connect, read, write, pool, and overall timeouts.
- Add bounded concurrency to `/healthz` and `/sickz` probes.
- Add an overall deadline for aggregated health responses.
- Separate liveness, readiness, and detailed dependency diagnostics.
- Validate configurable probe destinations to reduce SSRF risk.
- Replace remaining synchronous `requests` calls in async routes.

#### Acceptance criteria

- `/livez` performs no dependency I/O.
- `/readyz` checks only dependencies required to serve traffic.
- One slow dependency cannot indefinitely delay a health response.

### Priority 8: typing and dependency boundaries

#### Work

- Expand Pyright coverage module by module until the full `nabla/` package is
  checked within an acceptable runtime.
- Replace legacy `Dict`, `List`, untyped dictionaries, and broad `Any` values.
- Introduce `TypedDict`, Pydantic models, or protocols at external boundaries.
- Add explicit return types to route handlers and lifecycle helpers.
- Reduce optional dependencies imported by core modules.
- Consolidate package management around UV and remove obsolete Poetry, Pipenv,
  Conda, or duplicate Docker paths after confirming they are unused.

#### Acceptance criteria

- `pyright nabla` completes in CI and reports zero errors.
- Core application imports require only core runtime dependencies.
- The lockfile and declared dependency groups agree with CI and production.

### Priority 9: security and production hardening

#### Work

- Remove or tightly isolate remaining `verify=False` HTTP calls.
- Ensure operational endpoints never expose secrets or unredacted environment
  values.
- Review CORS origins, methods, credentials, and deployment-specific defaults.
- Add request-size limits and explicit rate limits to expensive AI/RAG routes.
- Normalize external errors before returning them to clients.
- Confirm SOPS files and generated secrets cannot be committed accidentally.
- Run dependency, container, and secret scans in CI.

#### Acceptance criteria

- Security scans run on every merge request.
- No endpoint returns credentials, tokens, DSNs, or raw provider payloads.
- TLS verification can only be disabled through an explicit, documented local
  development setting.

### Suggested CI pipeline

1. `ruff format --check nabla tests`
2. `ruff check nabla tests`
3. targeted Pyright, expanding toward `pyright nabla`
4. `pytest tests/unit`
5. `pytest -m integration` with PostgreSQL and Redis services
6. coverage enforcement
7. dependency and secret scanning
8. container build and vulnerability scanning

### Resume checklist

Before starting another improvement session:

1. Read this document and `AGENTS.md`.
2. Run `git status --short` and preserve unrelated user changes.
3. Do not edit `.env`, `.env.local`, `.env.secrets`, or SOPS material.
4. Run the baseline checks before changing code.
5. Select one priority and add tests that fail before applying its fix.
6. Update this roadmap when an item is completed, deferred, or superseded.

At the time this roadmap was created, `.pre-commit-config.yaml` already
contained user changes and `.env.sops.secrets` / `secrets.env.sops` were
untracked. They must not be overwritten, reformatted, deleted, or committed as
part of unrelated quality work.
