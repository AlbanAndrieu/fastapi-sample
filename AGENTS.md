# FastApi Sample (Sample) — Agent Guide

This document gives AI coding assistants the context needed to work effectively in this repository.

## What this service does

The Sample is a Python/FastAPI service that answers legal research queries using an agentic OpenRAG pipeline. It streams responses over SSE. Queries are received from OpenWebUI, not directly from this service.

---

## Tech stack

| Area | Choice |
|------|--------|
| Language | Python 3.12 |
| Web framework | FastAPI + uvicorn (dev) / gunicorn+uvicorn worker (prod) |
| Package management | UV (`uv.lock`) |
| LLM providers | Azure OpenAI, Anthropic, Google GenAI (multi-provider load balancer) throught LiteLLM |
| Observability | Langfuse (tracing + prompts), Prometheus metrics, optional Datadog |
| Feature flags | Statsig |
| Streaming | Server-Sent Events (`sse-starlette`) |
| Type checking | Pyright (basic mode) |
| Linting | Ruff (`.ruff.toml`) |
| Formatting | Ruff (`ruff format`; `[format]` in `.ruff.toml`) |

---

## Repository layout

```
legal-research-assistant/
├── main.py                     # ASGI entry: sets up logging + Langfuse, imports app
├── fastapi_server.py           # FastAPI app, lifespan, routes
├── nabla/
│   ├── api/
│   │   └── health_checks.py    # Health checks
│   └── ai/                     # All active application logic
│       └── chat_completion.py  # Chat completion
├── scripts/                    # Various helper script
├── docs/                       # Internal docs 
├── data/                       # Local test datasets
├── pyproject.toml              # Dependencies + tool config
├── pyrightconfig.json          # Pyright basic mode config
├── .ruff.toml                  # Ruff config
└── Dockerfile                  # Container build
```

---

## Key entry points

- **`main.py`** — Calls `setup_logging()` and `fetch_prompts_on_startup()`, then exports `app` from `fastapi_server`.
- **`fastapi_server.py`** — Defines the FastAPI `app`, lifespan (daily metadata maintenance + schema generation), and wires routes.
- **Health check:** `GET http://localhost:8091/health`

---

---

## Environment and configuration

- All env vars use `V2__` prefix with `__` as separator for nested settings (Pydantic nested models in `config_settings.py`).
- Mode-specific agent/retrieval behaviour and Statsig-gated overrides are in `backend/v2/config.py`.
- **Never edit per-repo `.env`, `.env.local`,  `.env.secrets` directly in the setup** —.

Key variables: `V2__AZURE__*` (LLM), `LANGFUSE_*`, `STATSIG_*`.

---

## Running locally

Use a **UV** CLI compatible with the lockfile (`poetry --version`). Regenerate `uv.lock` on (the file’s first line records the generator).

```bash
# Install (include test and format groups)
uv sync

# Start dev server
uvicorn main:app --host 0.0.0.0 --port 8091 --reload
```

PostgesSQP must be reachable before startup. Sample will fail to start if PG is down.

---

## Testing

```bash
pytest                  # run all tests
pytest tests/unit/      # unit tests only
pytest -m asyncio       # async tests
```

- Tests live under `tests/`
- Root `conftest.py` injects extensive mock `V2__*` env vars and disables Langfuse tracing.
- Coverage threshold: `--cov-fail-under=35` (CI enforced).
- Use `pytest-asyncio` for async tests; mark with `@pytest.mark.asyncio`.

---

## Code quality

### Ruff (`.ruff.toml`)

- Max McCabe complexity: **15** (relaxed from default 10 to accommodate inherently complex agent logic).
- Always enforced: security (`S`), errors (`E`, `F`), async rules (`ASYNC`), performance (`PERF`).
- Run: `ruff check .` / `ruff format .`

### Pyright (`pyrightconfig.json`)

**Basic mode** — do not expect strict enforcement. Key rules to follow anyway:

- Never pass `None` where a non-optional type is expected. Handle `Optional` explicitly.
- Ensure function return types match their signatures.
- Validate external data (API responses, ES results) at boundaries.
- Use `# type: ignore` sparingly and only when the type system cannot express the runtime behavior.
- Excluded from type checking: see `exclude` in `pyrightconfig.json` (includes `utility_scripts/`, `jm_gunicorn_logger.py`, tests, etc.).

---

## Important constraints

- **VPN may be required** for shared Elasticsearch / Back Office / Keycloak.
- **Langfuse prompts** are fetched at startup. Tests disable this via `LANGFUSE_TRACING_ENABLED=false`.
- **Statsig** controls feature flags and per-mode config overrides. Use `utils/statsig_manager.py` for flag checks.

---

## Evaluation

An end-to-end retrieval benchmark lives under `backend/v2/evaluation/` (Snakemake workflow). See `backend/v2/evaluation/README.md` for setup and usage. The REST endpoint `/evaluation/metrics` and `/auto-mode-selection/benchmark` are available when running the server.
