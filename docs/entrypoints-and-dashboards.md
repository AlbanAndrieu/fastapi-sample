# Application entry points and local dashboards

This document replaces the stale dashboard notes from pull request #63. The
current application serves HTTP, OpenAPI and MCP from the same FastAPI process;
FastAPI Radar is not installed and is not an MCP server.

## Application entry points

| Purpose | Command or module | Default URL |
| --- | --- | --- |
| FastAPI development | `uv run fastapi dev` | `http://127.0.0.1:8000` unless a port is supplied |
| Repository development | `uv run uvicorn server_all:app --reload --host 0.0.0.0 --port 8080` | `http://127.0.0.1:8080` |
| Docker Compose API | `docker compose up api` | `http://127.0.0.1:8080` |
| Production container | Gunicorn loads `server_all:app` | port `8080` |
| Python console script | `app` loads `server_app:app` | configured by `EXPOSE_HOST` and `EXPOSE_PORT` |

Use `server_all:app` for ASGI servers and deployment. Running
`python server_all.py` invokes the MCP object's native runner and is not the
normal FastAPI startup path.

## FastAPI and protocol endpoints

| Endpoint | Purpose | Availability |
| --- | --- | --- |
| `/docs` | Swagger UI generated from the complete application schema | Always |
| `/openapi.json` | OpenAPI schema used by Swagger UI and FastMCP | Always |
| `/mcp` | FastMCP Streamable HTTP transport | Always |
| `/a2a` | A2A JSON-RPC application | Only when `A2A_ENABLED` is true and its package imports |
| `/admin` | SQLAdmin UI | Controlled by the current Unleash configuration |
| `/ff` | Feature flags UI | Only when `DEBUG` is enabled |
| `/metrics` | Prometheus metrics | Always registered; operational access policy may require a key |
| `/health`, `/healthz`, `/sickz` | Health and detailed diagnostics | Detailed routes may require `DIAGNOSTICS_ACCESS_KEY` |
| `/api/homelab-services` | Public service catalog | Always |
| `/api/homelab-topology` | Service topology | May require `DIAGNOSTICS_ACCESS_KEY` |

The project-level [`.mcp.json`](../.mcp.json) and
[`opencode.json`](../opencode.json) both target
`http://127.0.0.1:8080/mcp`. Start the API first; neither configuration starts
a second dashboard process.

## Docker Compose dashboards

The repository Compose file also publishes independent development services:

| Service | URL | Notes |
| --- | --- | --- |
| Prometheus | `http://127.0.0.1:9090` | Reads `prometheus_data/prometheus.yml` |
| Grafana | `http://127.0.0.1:3000` | Uses the `grafana_data` volume |
| JupyterLab | `http://127.0.0.1:8888` | Development-only data-science image |

PostgreSQL and Redis bind only to loopback on ports 5432 and 6379. They are
service endpoints, not browser dashboards.

## FastAPI Radar decision

Pull request #63 attempted to launch `python -m fastapi_radar` on port 8091.
FastAPI Radar 0.3.4 is middleware mounted inside an existing FastAPI
application; it provides no module CLI and no MCP transport. Its dashboard can
record request and response bodies, headers, SQL and exceptions.

If Radar is introduced later, add it as one guarded feature with all of these
properties:

- disabled by default and disabled in production;
- an explicit authentication dependency;
- redaction rules for secrets, cookies, authorization headers and personal data;
- a documented retention policy for its DuckDB data;
- tests proving that disabled mode does not import or initialize it.

Do not add port 8091 or a fake OpenCode command until such a feature exists.
