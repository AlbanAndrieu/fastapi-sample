# Engineering and security roadmap

This document is the single planning source for future `fastapi-sample` pull
requests. Keep completed work, open follow-ups and intentional compatibility
exceptions here rather than creating additional todo or refactoring documents.

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

## Production audit — 2026-08-26

- `/api`, `/health`, `/openapi.json`, `/api/homelab-topology`,
  `/api/homelab/runtime` and `/mcp` remained reachable in FastAPI Cloud.
- `/healthz`, `/api/homelab-services` and `/api/homelab/health` returned 500
  because a merge retained the obsolete remote-cache implementation after its
  imports and state had been removed. The packaged catalog is now the only
  source and the production deployment smoke test exercises it.
- The Python workflow for PR #87 detected the resulting 15 Ruff errors but the
  red merge was accepted. Branch protection remains the final safeguard planned
  after CI stabilizes.
- FastAPI Cloud returned application tracebacks to public clients, which proves
  that `DEBUG` is enabled in the production environment. Set it to `false` in
  FastAPI Cloud; application code now parses all debug consumers consistently.

## P0 — Credentials and private data

- [ ] Set `DEBUG=false` in the FastAPI Cloud production environment and verify
      that unexpected exceptions no longer expose application tracebacks.
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
- [x] Apply the same optional diagnostic-key protection to the declared homelab
      topology endpoint without changing its open-by-default behavior.
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

- [x] Keep Vercel as a lightweight HTTP compatibility proxy to FastAPI Cloud
      instead of bundling the full Python dependency graph beyond the 500 MB limit.
- [x] Reconnect the Vercel project to GitHub; GitHub commits now receive the
      project’s Vercel deployment status.
- [ ] Trigger FastAPI Cloud deployment for the existing
      `semantic-release-published` repository dispatch.
- [ ] Check out the immutable release tag in validation and deployment jobs.
- [x] Verify the deployed release through the public `/health` version field and
      smoke-test the packaged homelab catalog after every workflow deployment.
- [x] Restore semantic release progression; releases `1.6.1` and `1.7.0`
      demonstrate that later `feat:` commits advance the project version.
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
- [ ] Finish the self-hosted Sentry integration at `sentry.albandrieu.com`:
      create a dedicated `fastapi-sample` project in the `sentry` organization
      instead of reusing the current `internal` project; configure its DSN through
      `SENTRY_DSN` for local and FastAPI Cloud runtimes; verify environment and
      release tagging, error capture and traces; create a separate least-privilege
      `SENTRY_ACCESS_TOKEN` for the official Sentry MCP `inspect` skill; and verify
      that MCP issue/event inspection works without granting project/team writes.
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
- [x] Align locked `esbuild` and `js-yaml` dependencies with existing secure npm
      overrides instead of suppressing Trivy vulnerability findings.
- [x] Exclude npm-generated `package-lock.json` from Prettier while retaining
      JSON parsing and dependency/security validation.
- [x] Keep the inverse `/sickz` certificate exception narrowly justified for
      both Ruff and Bandit instead of disabling TLS findings globally.
- [x] Align the Biome package, pre-commit hook and configuration schema on one
      pinned version.
- [x] Run Gitleaks through its native Go pre-commit hook so secret scanning does
      not require a local Docker daemon.
- [x] Remove the duplicate standalone Pylint workflow and keep the Python
      package workflow as the authoritative Pylint quality gate.
- [ ] Make relevant Trivy findings blocking once the current vulnerability
      baseline has been triaged.
- [ ] Reduce the current Trivy dependency baseline below 48 findings and lower
      its temporary regression ceiling of 55 as vulnerabilities are remediated.
- [ ] Pin every reusable GitHub Action to a verified immutable commit SHA.
- [ ] Protect `main`, require reviewed pull requests and enforce the final
      mandatory test/security checks after the current refactoring stabilizes.

## P2 — Runtime and database architecture

- [x] Avoid opening the auxiliary PostgreSQL connection pool during module
      import and close it explicitly during application shutdown.
- [x] Keep JSON log formatters safe while Python clears module globals at shutdown.
- [x] Use one environment-boolean parser for application debug, feature flags,
      telemetry and internal homelab probes.
- [x] Remove obsolete `uv_build` settings after standardizing the package on
      Hatchling, eliminating the conflicting-backend build warning.
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

## P2 — Search provider architecture

- [x] Group Tavily, Brave and Google routes under one `search` OpenAPI tag
      without changing their public paths or provider-specific response contracts.
- [ ] Add SearXNG to `nabla-compose`; it is not present on the current `master`
      branch. Pin the container image, enable JSON output, keep it behind the private
      network or an authenticated reverse proxy, and enable the limiter with Valkey
      if it becomes internet-accessible.
- [ ] Add an optional `/v1/searxng/search` adapter with a normalized response
      model, bounded timeout and explicit provider provenance.
- [ ] Enable SearXNG's official `braveapi` engine when a Brave API key is
      configured. Evaluate its keyless Brave web engine separately because HTML
      parsing has different reliability and provider-policy risks.
- [ ] Evaluate Google through SearXNG as a transitional source only; its web
      engine can encounter bot-protection responses, while Google's Custom Search
      JSON API is closed to new customers and scheduled to end for existing
      customers on 2027-01-01.
- [ ] Keep Tavily as a direct provider until a separate experiment proves that a
      SearXNG JSON/custom engine preserves its LLM-oriented scoring, content and
      answer metadata without exposing its API key in source control.
- [ ] Add a provider orchestrator above the adapters with per-provider budgets,
      timeouts, circuit breakers, deduplication and fallback policy. Do not make
      SearXNG a mandatory dependency for every search request.

## P2 — Local development and documentation

- [x] Make Docker Compose use the real `server_all:app` entrypoint and port 8080.
- [x] Bind local PostgreSQL and Redis ports to loopback by default.
- [x] Remove the notebook container's access to the host SSH directory.
- [x] Register diagnostic routes before MCP captures OpenAPI so Homelab catalog,
      topology and health endpoints remain visible in Swagger with typed schemas.
- [ ] Merge the two Compose files into one documented configuration with
      optional development, notebook and observability profiles.
- [x] Replace legacy Pipenv/Poetry instructions with a Python 3.13 + `uv`
      quickstart.
- [ ] Archive obsolete Dockerfiles after confirming that no deployment uses them.
- [x] Keep Vercel as a main-only HTTP compatibility rewrite to FastAPI Cloud;
      skip pull-request preview builds that would exceed the function-size limit.
- [ ] Deduplicate Cursor, Codex, OpenCode and Copilot instructions while keeping
      `AGENTS.md` as the concise shared policy.
- [ ] Store generated SBOM reports as CI artifacts instead of tracking large
      generated files.
- [ ] Continue the MCP SDK integration review:
      <https://github.com/modelcontextprotocol/python-sdk>.
- [ ] Evaluate a pfSense MCP server as a separate, private homelab service. Start
      with [night4me/pfsense-mcp-server](https://github.com/night4me/pfsense-mcp-server)
      in its default 95-tool read-only profile; compare
      [gensecaihq/pfsense-mcp-server](https://github.com/gensecaihq/pfsense-mcp-server)
      for guarded writes and
      [abl030/pfsense-mcp](https://github.com/abl030/pfsense-mcp) only when full
      OpenAPI-generated coverage is necessary.
      Require strict TLS, a least-privilege API credential, audit logs and no public
      exposure before enabling any mutating tool.

## PR #63 recovery ledger

The unmerged PR #63 changed 95 paths. Compared with the current PR branch,
11 are byte-identical, 64 have since diverged and 20 are absent. Recover changes
in reviewable batches; never overwrite newer fixes with the old blob wholesale.

- [x] Restore the global TrueNAS SDK instruction; current runtime code already
      follows it by lazily importing the official `truenas_api_client` package.
- [x] Restore the FastAPI agent skill in its official directory layout, including
      every referenced file, instead of the incomplete flat file from PR #63.
- [x] Restore `.mcp.json` and `opencode.json` against the application’s real
      Streamable HTTP endpoint at `http://127.0.0.1:8080/mcp`. The old PR #63
      `python -m fastapi_radar` command is not restored because FastAPI Radar 0.3.4
      exposes neither a module CLI nor an MCP server.
- [ ] Evaluate FastAPI Radar as one coherent, optional local-development feature:
      dependency and lock, ignored DuckDB file, application instrumentation,
      dashboard discovery and accurate security documentation. Keep it disabled in
      production because it records request/response bodies and headers.
- [ ] Compare the three missing RAG modules and their tests with the newer
      deep-agent/external integration architecture; port behavior, not stale files.
- [ ] Compare the missing TrueNAS route/service modules and mapping tests with
      the consolidated official-client adapter and Homelab response models.
- [x] Rewrite `docs/entrypoints-and-dashboards.md` for the current application,
      MCP transport and Compose services.
- [x] Reconcile README startup examples and links with port 8080,
      `server_all:app` and the canonical `/mcp` transport.
- [ ] Rewrite `scripts/discover_dashboards.py` only if machine-readable dashboard
      discovery is still useful; the PR #63 parser targets invalid OpenCode fields.
- [ ] Review the missing SQL snapshot and `panda.py` separately for necessity,
      generated-content policy and secret exposure before restoring either file.
- [x] Restore the PR #63 Langfuse skill update as one locked bundle: prompt
      engineering, v4 project migration, instrumentation self-audit and SDK upgrade
      guidance.
- [ ] Review every divergent workflow, dependency and application file against
      current CI results; apply small semantic patches with focused tests.
- [x] Record an explicit retained, superseded or restored decision for every one
      of the 20 absent PR #63 paths before closing this recovery effort.

### PR #63 absent-path disposition

| PR #63 path                                                  | Decision               | Reason                                                                                               |
| ------------------------------------------------------------ | ---------------------- | ---------------------------------------------------------------------------------------------------- |
| `.agents/skills/fastapi-SKILL.md`                            | Adapted                | Restored as the complete official `.agents/skills/fastapi/` bundle so relative references resolve.   |
| `.agents/skills/langfuse/references/prompt-engineering.md`   | Restored               | Part of the locked Langfuse skill update.                                                            |
| `.agents/skills/langfuse/references/v4-project-migration.md` | Restored               | Part of the locked Langfuse skill update.                                                            |
| `.github/instructions/memory.instruction.md`                 | Restored               | Preserves the official TrueNAS SDK rule.                                                             |
| `.mcp.json`                                                  | Adapted                | Points clients at the application’s real Streamable HTTP `/mcp` endpoint.                            |
| `TODO.md`                                                    | Retained deletion      | Its content is consolidated in this roadmap.                                                         |
| `docs/entrypoints-and-dashboards.md`                         | Adapted                | Rewritten for the current ASGI entry point, port 8080, MCP mount and Compose dashboards.             |
| `nabla/api/rag.py`                                           | Deferred semantic port | The old synchronous route depends on a blocking, process-global vector store.                        |
| `nabla/api/services.py`                                      | Deferred semantic port | The old async route performs blocking `requests` and leaks raw integration errors.                   |
| `nabla/api/truenas_apps_api.py`                              | Superseded             | Its router alias targets an object that no longer exists after TrueNAS consolidation.                |
| `nabla/integrations/external_rag.py`                         | Deferred semantic port | Replace synchronous `requests`, import-time environment reads and swallowed exceptions.              |
| `nabla/integrations/truenas_api_ws.py`                       | Superseded             | Current `nabla/integrations/truenas_client.py` owns the official SDK adapter and safer TLS defaults. |
| `nabla/rag/ingest.py`                                        | Deferred redesign      | Avoid the mutable global store, duplicate ingestion and blocking parsing in request/lifespan paths.  |
| `opencode.json`                                              | Adapted                | Uses OpenCode’s documented `mcp.remote` schema instead of fake command metadata.                     |
| `panda.py`                                                   | Deferred               | Restore only through a validated CLI entry point with argument handling.                             |
| `scripts/discover_dashboards.py`                             | Deferred rewrite       | Its parser relies on the invalid PR #63 OpenCode schema.                                             |
| `sql/schema-2026-07-17.sql`                                  | Superseded             | Alembic is the migration source of truth; do not add a duplicate generated snapshot.                 |
| `tests/unit/test_main_wiring.py`                             | Deferred semantic port | It asserts an old MCP resource function removed by the newer application wiring.                     |
| `tests/unit/test_rag_ingest.py`                              | Deferred with RAG      | Its expectations encode the unsafe global vector-store implementation.                               |
| `tests/unit/test_truenas_service_mapping.py`                 | Superseded             | Current TrueNAS tests cover the consolidated adapter and current keyword-only mapping API.           |

“Deferred semantic port” means that the capability remains planned, but the old
file must not be copied into the current application unchanged.

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

#### application factory and import safety work

- Introduce `create_app(settings)` instead of constructing the application at
  module import time.
- Move router registration into a dedicated function or module.
- Move middleware and observability configuration out of `nabla/main.py`.
- Move MCP and A2A mounting into explicit application setup functions.
- Ensure importing an API model, router, or test helper does not create pools,
  threads, SDK clients, tracers, or network requests.
- Replace the remaining global database and Redis clients with resources owned
  by `app.state` or injected dependencies.

#### application factory and import safety acceptance criteria

- A unit test can create a minimal application without PostgreSQL, Redis,
  Statsig, Unleash, Datadog, Sentry, MCP, or RAG.
- `python -c "import nabla.main"` performs no external network request.
- Two application instances can be created in one process without duplicate
  middleware, routes, metrics, or background tasks.

### Priority 2: lifecycle resilience

#### lifecycle resilience work

- [x] Use `contextlib.AsyncExitStack` to manage startup resources.
- [x] Close Redis, PostgreSQL pools and MCP clients explicitly during shutdown.
- [x] Align the locked redis-py version with the asynchronous `aclose()`
      lifecycle API and validate the real installed client contract without mocks.
- [x] Roll back partially completed startup when a later dependency fails.
- [x] Add stable names to application-owned background tasks.
- [x] Add structured error reporting to background tasks.
- [x] Keep optional metrics and Redis listener failures isolated from request
      handling; report their task name and exception type without automatic restart.
- [x] Add startup and shutdown tests for success, partial failure, and cancellation.

#### lifecycle resilience acceptance criteria

- [x] Every acquired resource is released after normal shutdown and failed startup.
- [x] No watcher, thread, pool, task, or client remains alive after lifecycle tests.
- Shutdown completes within a documented timeout.

### Priority 3: integration tests

#### integration tests work

- Migrate the remaining `TestClient` suites to `httpx.AsyncClient` and
  `ASGITransport` where appropriate.
- Provide containerized PostgreSQL and Redis fixtures for tests marked
  `integration`.
- Run web rendering tests separately with `pytest -m webtest`.
- Remove environment-dependent skips where a deterministic fake or container
  can be used.
- Add a CI job for `pytest -m integration`.
- Keep unit tests network-disabled by default.

#### integration tests acceptance criteria

- `pytest tests/unit` requires no external service and remains deterministic.
- `pytest -m integration` either provisions its dependencies or fails with a
  clear prerequisite message.
- Tests never silently convert failures into successful exit codes.

### Priority 4: Datadog and observability isolation

### Current issue

Direct Datadog imports previously loaded the SDK through database and route
modules even when tracing was disabled. The profiler also started during module
import and had no application-owned shutdown.

#### Datadog and observability isolation work

- [x] Load Datadog tracing modules only when `DD_TRACE_ENABLED=true`.
- [x] Remove direct tracer imports from database and route modules.
- [x] Own profiler startup and shutdown in the application lifespan.
- [x] Configure profiling independently with `DD_PROFILING_ENABLED`.
- [x] Remove the global placeholder user assignment and keep Datadog PII
      disabled until authenticated request identity is available.
- [x] Keep Sentry PII disabled and make trace, profile and error sampling
      configurable with conservative defaults.
- [x] Verify that disabled Datadog paths do not import the SDK.

#### Datadog and observability isolation acceptance criteria

- [x] Unit tests finish without Datadog warnings, five-second tracer waits, or
      logging errors.
- [x] Disabled Datadog instrumentation has no SDK import-time side effect.
- [x] Production configuration documents tracing, profiling and PII choices.

### Priority 5: Notes domain cleanup

#### Notes domain cleanup work

- Replace legacy SQLAlchemy declarative models and `databases.Record` with one
  consistent SQLAlchemy 2 or SQLModel data-access approach.
- [x] Replace synchronous note creation with asynchronous database queries and
      return the persisted database identifier.
- [x] Fix note updates to use the requested identifier and preserve the original
      creation timestamp.
- Change `Note.completed` from a string column to a boolean column through an
  Alembic migration.
- Store `created_date` as a timezone-aware timestamp and serialize it only at
  the API boundary.
- [x] Generate note response timestamps per instance instead of freezing them
      when the models module is imported.
- [x] Remove synchronous DB session work from asynchronous Notes request
      handlers.
- [x] Add response models for note creation and update operations.
- Add response models for read and delete operations.
- [x] Require Redis enqueue after persisting note updates; return HTTP 503 when
      the update succeeded but background processing is unavailable.
- [x] Restore the note-update regression test and cover asynchronous CRUD plus
      Redis queue failure.

#### Notes domain cleanup acceptance criteria

- Database and API types agree for IDs, booleans, and timestamps.
- Notes CRUD has unit and integration coverage for success, validation,
  rollback, missing records, and queue failures.
- No synchronous database call blocks the event loop.

### Priority 6: RAG architecture

#### RAG architecture work

- Replace the mutable global `VECTOR_DB` with a `VectorStore` protocol.
- Provide an in-memory implementation for tests and a persistent implementation
  for production.
- Protect ingestion and search from concurrent mutation.
- Avoid duplicate ingestion when files change or the application restarts.
- Validate embedding model and vector dimensions against stored vectors.
- Add bounded concurrency, timeouts, and structured errors around embeddings.
- Move document parsing dependencies behind optional integration boundaries.

#### RAG architecture acceptance criteria

- Search is deterministic under concurrent ingestion.
- Restarting the application does not duplicate existing chunks.
- Provider failures return a controlled API error rather than leaking raw
  exceptions.

### Priority 7: outbound HTTP and health checks

#### outbound HTTP and health checks work

- Create shared lifespan-owned `httpx.AsyncClient` instances.
- Define consistent connect, read, write, pool, and overall timeouts.
- Add bounded concurrency to `/healthz` and `/sickz` probes.
- Add an overall deadline for aggregated health responses.
- Separate liveness, readiness, and detailed dependency diagnostics.
- Validate configurable probe destinations to reduce SSRF risk.
- Replace remaining synchronous `requests` calls in async routes.

#### outbound HTTP and health checks acceptance criteria

- `/livez` performs no dependency I/O.
- `/readyz` checks only dependencies required to serve traffic.
- One slow dependency cannot indefinitely delay a health response.

### Priority 8: typing and dependency boundaries

#### typing and dependency boundaries work

- Expand Pyright coverage module by module until the full `nabla/` package is
  checked within an acceptable runtime.
- Replace legacy `Dict`, `List`, untyped dictionaries, and broad `Any` values.
- Introduce `TypedDict`, Pydantic models, or protocols at external boundaries.
- Add explicit return types to route handlers and lifecycle helpers.
- Reduce optional dependencies imported by core modules.
- Consolidate package management around UV and remove obsolete Poetry, Pipenv,
  Conda, or duplicate Docker paths after confirming they are unused.

#### typing and dependency boundaries acceptance criteria

- `pyright nabla` completes in CI and reports zero errors.
- Core application imports require only core runtime dependencies.
- The lockfile and declared dependency groups agree with CI and production.

### Priority 9: security and production hardening

#### security and production hardening work

- Remove or tightly isolate remaining `verify=False` HTTP calls.
- Ensure operational endpoints never expose secrets or unredacted environment
  values.
- Review CORS origins, methods, credentials, and deployment-specific defaults.
- Add request-size limits and explicit rate limits to expensive AI/RAG routes.
- Normalize external errors before returning them to clients.
- Confirm SOPS files and generated secrets cannot be committed accidentally.
- Run dependency, container, and secret scans in CI.

#### security and production hardening acceptance criteria

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


## Observability log qualification debt

- Revisit the DEBUG / INFO / WARNING / ERROR taxonomy across health and integration probes.
- Treat failures of required infrastructure dependencies such as the TrueNAS API as ERROR, while keeping intentionally disabled optional integrations at WARNING/INFO.
- Preserve sanitized failure phase/stage metadata for Sentry without logging credentials or secret values.
- Add Sentry fingerprinting/rate limiting for periodic health failures so a 30-second probe cache cannot create duplicate incident noise.
