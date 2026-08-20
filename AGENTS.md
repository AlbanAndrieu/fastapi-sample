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

## Nabla: `/healthz`, `/sickz`, and LAN vs cloud

- **Routes:** [`nabla/main.py`](nabla/main.py) exposes `GET /healthz` (deep dependency JSON) and `GET /sickz` (inverse reachability JSON, `ORJSONResponse`). `/healthz` also requires HTTPS reachability of a fixed set of `*.albandrieu.com` endpoints (see [`nabla/api/health_checks.py`](nabla/api/health_checks.py) `_ALBANDRIEU_HEALTHZ_HTTPS`). Default `/sickz` targets include pfSense plus internal-only `*.albandrieu.com` hosts (see `config_settings._ALBANDRIEU_SICKZ_HOSTNAMES`).
- **Probe logic:** [`nabla/api/health_checks.py`](nabla/api/health_checks.py) (`build_healthz_payload`, `build_sickz_payload`). Settings: [`nabla/config_settings.py`](nabla/config_settings.py) (`SICKZ_*`).
- **`SICKZ_INTERNAL_NETWORK`:** Set `true` when this process runs in the same trust zone as pfSense (e.g. home LAN) so `/sickz` skips HTTP probes that pfSense would answer. Leave `false` on cloud or any host that must not reach the firewall UI. **Implicit LAN skip** also applies when `SICKZ_NETWORK_LABEL` is exactly `nabla` (case-insensitive) or when module `APP_DOMAIN` is `albandrieu.albandrieu.com`, unless a known PaaS runtime is detected. **There is no full auto-proof of “same network as pfSense”** from bind address alone (`0.0.0.0` does not imply LAN); combine flags, implicit rules, and inventory per deployment.
- **Docker:** Containers often see a bridge IP (e.g. `172.17.0.1`) that is not your whole home subnet. Prefer the explicit flag (and `network_mode: host` only when you intentionally need host networking). Optional `SICKZ_TARGETS` groups use `|` for equivalent URLs (hostname vs gateway).
- **`SICKZ_TARGETS` / `SICKZ_NETWORK_LABEL`:** See field descriptions in `config_settings.py`; `SICKZ_NETWORK_LABEL` falls back to `APP_DOMAIN` for messages.
- **Known PaaS:** If the runtime looks like Vercel, Kubernetes, Lambda, Fly, Railway, or Heroku (`DYNO`), `/sickz` **never** skips probes for internal LAN (even if `SICKZ_INTERNAL_NETWORK=true`), so isolation checks stay meaningful on managed platforms. The JSON `runtime` object includes `cloud_paas_detected`, `sickz_internal_network_config`, and `sickz_internal_network_effective`.

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

### Maintainability and file size

Before modifying a source file, assess both its size and its responsibilities.

- Python files above **400 lines** are a maintainability warning. Prefer extracting cohesive modules instead of adding unrelated responsibilities.
- Python files above **700 lines** must normally be refactored before significant new functionality is added, unless the file is generated, a migration, or inherently declarative.
- Functions above roughly **60 lines** should be reviewed for extraction; functions above **100 lines** should normally be refactored.
- Classes above roughly **250 lines** should be reviewed; classes above **400 lines** should normally be split by responsibility.
- Avoid module-level initialization that performs network calls, opens database connections, starts telemetry exporters, or initializes feature-flag SDKs. Prefer lazy factories, dependency injection, or FastAPI lifespan initialization.
- When using an API that replaces a complete file, never submit a partial file body. Fetch the complete current file, transform it, validate the result, then replace it.
- The repository enforces modified Python file size with `scripts/check_code_size.py`: warning above 400 lines and failure above 700 lines. Generated code and migrations are excluded explicitly.

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
