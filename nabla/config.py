"""Central configuration for the FastAPI application."""

import os
import warnings

from pydantic.json_schema import PydanticJsonSchemaWarning

from nabla.utils.environment import env_bool

# Datadog setup
_DATADOG_ENABLED = env_bool("DATADOG_ENABLED")
if not _DATADOG_ENABLED:
    os.environ["DD_TRACE_ENABLED"] = "false"
    os.environ["DD_LOGS_INJECTION"] = "false"
    os.environ["DD_PROFILING_ENABLED"] = "false"
    os.environ["DD_APPSEC_ENABLED"] = "false"
    os.environ["DD_IAST_ENABLED"] = "false"

# Feature flags
UNLEASH_ENABLED = env_bool("UNLEASH_ENABLED")

# Suppress warnings
warnings.filterwarnings(
    "ignore",
    category=PydanticJsonSchemaWarning,
    message=".*non-serializable-default.*",
)

# CORS origins. Origins must not include a trailing slash.
CORS_ORIGINS = [
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:8091",
    "http://localhost:8001",
    "https://fastapi-sample.service.gra.dev.consul",
    "https://fastapi-sample.service.gra.uat.consul",
    "https://fastapi-sample.fastapicloud.dev",
    "https://www.albanandrieu.com",
]

# MCP allowed routes. Runtime diagnostics only exist when the local opt-in router
# is registered; keeping them here does not make them available in production.
MCP_ALLOWED_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/v1/tavily/search"),
        ("POST", "/v1/brave/search"),
        ("POST", "/v1/google/search"),
        ("GET", "/v1/runtime/metadata"),
        ("GET", "/v1/runtime/logs"),
        ("GET", "/v1/runtime/errors"),
        ("GET", "/v2/version"),
        ("GET", "/v2/profile/search"),
        ("GET", "/demo/greet_user/{name}"),
        ("GET", "/demo/get_time"),
        ("GET", "/demo/add"),
        ("GET", "/demo/multiply"),
    },
)

# Noisy paths to exclude from detailed logging
NOISY_SUCCESS_PATHS = {
    "/api/homelab-services",
    "/api/homelab/health",
    "/api/health-board",
    "/docs",
    "/docs/oauth2-redirect",
    "/health",
    "/healthz",
    "/livez",
    "/logs",
    "/metrics",
    "/openapi.json",
    "/ping",
    "/redoc",
    "/readyz",
    "/sickz",
    "/stream",
    "/v1/runtime/errors",
    "/v1/runtime/logs",
    "/v1/runtime/metadata",
}
NOISY_SUCCESS_PREFIXES = ("/mcp", "/logs/", "/stream/", "/v1/mcp/")
