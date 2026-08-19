# ruff: noqa: E402 -- Datadog opt-out environment must be set before SDK imports.
# pylint: disable=wrong-import-position

"""FastAPI application factory and initialization."""

import argparse
import os
from contextlib import asynccontextmanager

from ddtrace import config, patch, tracer
from ddtrace.contrib.trace_utils import set_user
from ddtrace.profiling import Profiler
from ddtrace.trace import TraceFilter
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastmcp import FastMCP
from fastmcp.server.providers.openapi.routing import MCPType
from pybreaker import CircuitBreaker
from prometheus_fastapi_instrumentator import Instrumentator
from sqladmin import Admin
from starlette.middleware.cors import CORSMiddleware

from nabla.api import (
    appwrite_route,
    brave_route,
    demo,
    google_search_route,
    info,
    integration,
    keycloak,
    mcp_ops_route,
    ping,
    sensor,
    tavily_route,
    users,
    v1,
    v2,
)
from nabla.api.auth import keycloak as keycloak_auth
from nabla.api.db.database import engine
from nabla.api.notes import notes
from nabla.api.users.models import UserAdmin, UserCreate, UserRead, UserUpdate
from nabla.api.users.users import fastapi_users, jwt_backend
from nabla.config import CORS_ORIGINS, MCP_ALLOWED_ROUTES, UNLEASH_ENABLED
from nabla.config_settings import (
    APP_NAME,
    APP_PREFIX_VERSION,
    APP_RUNTIME_VERSION,
    APP_VERSION,
    DD_TRACE_ENABLED,
    OTEL_SDK_DISABLED,
    OTLP_GRPC_ENDPOINT,
    client,
    get_settings,
)
from nabla.deepagents import workflow as ai_workflow
from nabla.lifespan import lifespan as app_lifespan
from nabla.middleware import logging_middleware, metrics_middleware
from nabla.routes import register_routes, templates
from nabla.utils.log_config import setup_logging
from nabla.utils.logger import logger
from nabla.utils.logfire_config import configure_logfire
from nabla.utils.prometheus import PrometheusMiddleware, setting_otlp
from nabla.utils.sentry_config import configure_sentry

setup_logging()
logger.info("Creating API")

circuit_breaker_web = CircuitBreaker(fail_max=2, reset_timeout=10)

if DD_TRACE_ENABLED:
    patch(fastapi=True)
    config.fastapi["service_name"] = APP_NAME

    class FilterbyName(TraceFilter):
        """Filter out specific spans from traces."""

        def process_trace(self, trace):
            for span in trace:
                if span.name == "get_quote":
                    return None
            return trace

    tracer.configure(trace_processors=[FilterbyName()])

_DD_PROFILING_ENABLED = DD_TRACE_ENABLED and os.environ.get(
    "DD_PROFILING_ENABLED", "false"
).lower() in ("true", "1", "yes")
if _DD_PROFILING_ENABLED:
    prof = Profiler(env="prod", service=APP_NAME)
    prof.start()


@asynccontextmanager
async def combined_lifespan(app: FastAPI):
    """Combine application lifespan with MCP lifespan."""
    async with app_lifespan(app):
        async with mcp_app.lifespan(app):
            yield


def _configure_unleash_middleware(app: FastAPI) -> None:
    """Apply middleware based on Unleash feature flags."""
    if not UNLEASH_ENABLED:
        logger.warning("UNLEASH integration disabled via env variable")
        return

    if client.is_enabled("rate_limiter"):
        from fastapi.responses import JSONResponse
        from slowapi.errors import RateLimitExceeded

        app.add_exception_handler(
            RateLimitExceeded,
            lambda r, e: JSONResponse(
                status_code=429, content={"error": "Too Many Requests"}
            ),
        )
    else:
        logger.warning("Feature flag: rate_limiter not enabled")

    if client.is_enabled("cors"):
        app.add_middleware(
            CORSMiddleware,
            allow_origins=CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=["*"],
        )
    else:
        logger.warning("Feature flag: cors not enabled")

    if client.is_enabled("logging_metrics"):
        app.add_middleware(PrometheusMiddleware, app_name=APP_NAME)
    else:
        logger.warning("Feature flag: logging_metrics not enabled")


def _configure_metrics(app: FastAPI) -> None:
    """Configure Prometheus metrics instrumentation."""
    settings = get_settings()
    if settings.metrics_enabled:
        instrumentator = Instrumentator(
            should_group_status_codes=False,
            should_ignore_untemplated=True,
            should_respect_env_var=True,
            should_instrument_requests_inprogress=True,
            excluded_handlers=[
                "/metrics",
                "/health",
                "/healthz",
                "/sickz",
                "/v1/version",
                "/v2/version",
                "openapi.json",
                "docs",
            ],
            env_var_name="ENABLE_METRICS",
            inprogress_name="http_requests_in_progress",
            inprogress_labels=True,
        ).instrument(app)
        instrumentator.expose(app=app, include_in_schema=False)

    if not OTEL_SDK_DISABLED and OTLP_GRPC_ENDPOINT:
        setting_otlp(app, APP_NAME, OTLP_GRPC_ENDPOINT)
    elif not OTEL_SDK_DISABLED:
        logger.warning("OpenTelemetry enabled without OTLP_GRPC_ENDPOINT")


def _register_routers(app: FastAPI) -> None:
    """Register API routers."""
    app.include_router(ping.router, tags=["ping"])
    app.include_router(
        fastapi_users.get_auth_router(jwt_backend), prefix="/auth/jwt", tags=["auth"]
    )
    app.include_router(
        fastapi_users.get_register_router(UserRead, UserCreate), prefix="/auth", tags=["auth"]
    )
    app.include_router(
        fastapi_users.get_reset_password_router(), prefix="/auth", tags=["auth"]
    )
    app.include_router(
        fastapi_users.get_verify_router(UserRead), prefix="/auth", tags=["auth"]
    )
    app.include_router(
        fastapi_users.get_users_router(UserRead, UserUpdate), prefix="/users", tags=["auth"]
    )
    app.include_router(v1.router, tags=["api"])
    app.include_router(v2.router, tags=["api"])
    app.include_router(appwrite_route.router, tags=["appwrite"])
    app.include_router(tavily_route.router, tags=["tavily"])
    app.include_router(brave_route.router, tags=["brave"])
    app.include_router(google_search_route.router, tags=["google"])
    app.include_router(integration.router, tags=["integration"])
    app.include_router(demo.router, tags=["integration"])
    app.include_router(notes.router, tags=["notes"])
    app.include_router(info.router, tags=["test"])
    app.include_router(ai_workflow.router, tags=["ai"])
    app.include_router(mcp_ops_route.router, tags=["mcp-ops"])
    app.include_router(keycloak_auth.router, tags=["keycloak"])
    app.include_router(users.router, tags=["users"])
    app.include_router(sensor.router, tags=["sensor"])

    if os.getenv("DEBUG"):
        from fastapi_featureflags import router as ff_router

        app.include_router(ff_router, prefix="/ff", tags=["FeatureFlags"])

    from nabla.api.demo.socket.websocket import websocket_endpoint

    app.add_api_websocket_route("/ws/sensor", websocket_endpoint)


def _configure_mcp(app: FastAPI) -> None:
    """Expose MCP Streamable HTTP on the canonical /mcp endpoint."""
    from fastmcp.server.providers.openapi.routing import HTTPRoute

    def filter_route(route: HTTPRoute, default_type: MCPType) -> MCPType | None:
        if (route.method, route.path) in MCP_ALLOWED_ROUTES:
            return None
        return MCPType.EXCLUDE

    global mcp, mcp_app
    mcp = FastMCP.from_fastapi(app=app, name="mcp", route_map_fn=filter_route)

    # FastMCP owns the complete `/mcp` transport path. Mounting an app whose
    # internal path is `/` below `/mcp` makes clients/proxies depend on slash
    # redirects. Open WebUI expects a canonical Streamable HTTP endpoint.
    mcp_app = mcp.http_app(path="/mcp")
    app.mount("/", mcp_app)
    logger.info("MCP Streamable HTTP exposed at /mcp")

    if get_settings().a2a_enabled:
        try:
            from nabla.a2a_app import build_a2a_starlette_application

            app.mount("/a2a", build_a2a_starlette_application())
            logger.info("A2A JSON-RPC mounted at /a2a")
        except ImportError as exc:
            logger.warning("A2A mount skipped: %s", exc)


def _configure_admin_panel(app: FastAPI) -> None:
    """Configure SQLAdmin panel."""
    if not UNLEASH_ENABLED or client.is_enabled("admin_panel"):
        Admin(app, engine, title="Example: SQLAlchemy").add_view(UserAdmin)


def _configure_hot_reload(app: FastAPI) -> None:
    """Configure hot reload for development mode."""
    if os.getenv("DEBUG"):
        import arel

        async def reload_data():
            print("Reloading server data...")

        hot_reload = arel.HotReload(
            paths=[arel.Path("./nabla/data", on_reload=[reload_data]), arel.Path("./nabla/static"), arel.Path("./templates")],
        )
        app.add_websocket_route("/hot-reload", route=hot_reload)
        app.add_event_handler("startup", hot_reload.startup)
        app.add_event_handler("shutdown", hot_reload.shutdown)
        templates.env.globals["DEBUG"] = True
        templates.env.globals["hot_reload"] = hot_reload


def _setup_datadog_user_info() -> None:
    """Setup Datadog user context only when Datadog tracing is enabled."""
    if not DD_TRACE_ENABLED:
        return
    set_user(
        tracer,
        "usr.id",
        name="AlbanAndrieu",
        email=os.environ.get("MAIL_FROM", "alban.andrieu@gmail.com"),
        scope="sample_scope",
        role="manager",
        session_id="id_session",
        propagate=True,
    )


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        lifespan=combined_lifespan,
        title=f"{APP_NAME} {APP_PREFIX_VERSION}",
        description="FastAPI Sample for demo",
        version=APP_RUNTIME_VERSION,
        debug=os.getenv("DEBUG", "False").lower() == "true",
    )

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        openapi_schema = get_openapi(
            title="Custom title",
            version=APP_VERSION,
            summary="This is a very custom OpenAPI schema",
            description="Here's a longer description of the custom **OpenAPI** schema",
            routes=app.routes,
        )
        openapi_schema["info"]["x-logo"] = {"url": "https://fastapi.tiangolo.com/img/logo-margin-logo-teal.png"}
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi
    app.add_middleware("http", logging_middleware)
    app.add_middleware("http", metrics_middleware)
    _configure_unleash_middleware(app)
    _configure_metrics(app)
    _register_routers(app)
    _configure_mcp(app)
    _configure_admin_panel(app)
    _configure_hot_reload(app)
    configure_logfire(app, service_name=APP_NAME, service_version=APP_VERSION)
    configure_sentry()
    _setup_datadog_user_info()
    register_routes(app)
    return app


mcp = None
mcp_app = None
app = create_app()

parser = argparse.ArgumentParser(prog="nabla")
parser.add_argument("echo", help="String to print back to the console")


def main():
    """CLI entry point."""
    args = parser.parse_args()
    print(args.echo)


if __name__ == "__main__":
    main()
