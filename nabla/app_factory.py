# ruff: noqa: PLC0415 -- subsystem integrations stay lazy so disabled features are never imported.

"""FastAPI application factory with explicit subsystem switches.

``create_app()`` with default features builds the production application
exported by ``nabla.main``. ``create_minimal_app()`` builds a local diagnostics
application without PostgreSQL, Redis, observability, MCP or RAG side effects:

    uv run uvicorn --factory nabla.app_factory:create_minimal_app
"""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.openapi.utils import get_openapi
from starlette.routing import Route

from nabla.access_control import operations_access_middleware
from nabla.api import demo, info, integration, keycloak, v1, v2
from nabla.api import appwrite_route, brave_route, google_search_route, ping, tavily_route
from nabla.api.db.availability import require_database
from nabla.api.runtime_environment import application_debug_enabled
from nabla.app_features import AppFeatures
from nabla.config import UNLEASH_ENABLED
from nabla.config_settings import APP_NAME, APP_PREFIX_VERSION, APP_RUNTIME_VERSION, APP_VERSION, get_settings
from nabla.feature_flags import unleash_is_configured
from nabla.lifespan import build_lifespan
from nabla.middleware import logging_middleware, metrics_middleware
from nabla.rate_limit import configure_rate_limiting
from nabla.routes import register_routes, templates
from nabla.utils.environment import env_bool
from nabla.utils.logger import logger

__all__ = ["AppFeatures", "create_app", "create_minimal_app"]


def _build_app_lifespan(features: AppFeatures):
    """Combine the application lifespan with the enabled process-local lifecycles."""
    app_lifespan = build_lifespan(features)

    @asynccontextmanager
    async def combined_lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            if features.observability:
                _enter_profilers(stack)
            await stack.enter_async_context(app_lifespan(app))
            mcp_app = getattr(app.state, "mcp_app", None)
            if mcp_app is not None:
                await stack.enter_async_context(mcp_app.lifespan(app))
            yield

    return combined_lifespan


def _enter_profilers(stack: AsyncExitStack) -> None:
    """Start Pyroscope/Datadog profilers and register their shutdown."""
    from nabla.config_settings import DD_PROFILING_ENABLED, PYROSCOPE_ENABLED, PYROSCOPE_ENDPOINT
    from nabla.utils.datadog_config import start_datadog_profiler, stop_datadog_profiler
    from nabla.utils.pyroscope_config import start_pyroscope, stop_pyroscope

    pyroscope_started = start_pyroscope(
        enabled=PYROSCOPE_ENABLED,
        application_name=APP_NAME,
        server_address=PYROSCOPE_ENDPOINT,
    )
    stack.callback(stop_pyroscope, pyroscope_started)
    profiler = start_datadog_profiler(enabled=DD_PROFILING_ENABLED, app_name=APP_NAME)
    stack.callback(stop_datadog_profiler, profiler)


def _configure_unleash_middleware(app: FastAPI) -> None:
    """Apply middleware based on Unleash feature flags."""
    if not UNLEASH_ENABLED:
        logger.warning("UNLEASH integration disabled via env variable")
        return
    if not unleash_is_configured():
        logger.warning("UNLEASH_ENABLED is true but UNLEASH_INSTANCE_ID is missing; feature-flag middleware is disabled")
        return

    # Unleash is an optional remote control plane. Application construction must
    # never wait for GitLab DNS/network availability. Keep the safe local defaults
    # and let runtime feature-flag consumers observe Unleash independently.
    logger.warning(
        "UNLEASH configured as optional; startup skips remote feature-flag evaluation",
    )


def _configure_metrics(app: FastAPI) -> None:
    """Configure Prometheus metrics instrumentation and OTLP export."""
    from nabla.config_settings import OTEL_SDK_DISABLED, OTLP_GRPC_ENDPOINT

    settings = get_settings()
    if settings.metrics_enabled:
        from prometheus_fastapi_instrumentator import Instrumentator

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
        from nabla.utils.prometheus import setting_otlp

        setting_otlp(app, APP_NAME, OTLP_GRPC_ENDPOINT)
    elif not OTEL_SDK_DISABLED:
        logger.warning("OpenTelemetry enabled without OTLP_GRPC_ENDPOINT")


# PostgreSQL is optional at startup: DB-backed routers answer 503 when it is down.
_DATABASE_REQUIRED = [Depends(require_database)]


def _register_auth_routers(app: FastAPI) -> None:
    """Register the fastapi-users routers backed by PostgreSQL."""
    from nabla.api.users.models import UserCreate, UserRead, UserUpdate
    from nabla.api.users.users import fastapi_users, jwt_backend

    app.include_router(fastapi_users.get_auth_router(jwt_backend), prefix="/auth/jwt", tags=["auth"], dependencies=_DATABASE_REQUIRED)
    app.include_router(fastapi_users.get_register_router(UserRead, UserCreate), prefix="/auth", tags=["auth"], dependencies=_DATABASE_REQUIRED)
    app.include_router(fastapi_users.get_reset_password_router(), prefix="/auth", tags=["auth"], dependencies=_DATABASE_REQUIRED)
    app.include_router(fastapi_users.get_verify_router(UserRead), prefix="/auth", tags=["auth"], dependencies=_DATABASE_REQUIRED)
    app.include_router(fastapi_users.get_users_router(UserRead, UserUpdate), prefix="/users", tags=["auth"], dependencies=_DATABASE_REQUIRED)


def _register_routers(app: FastAPI, *, debug: bool, features: AppFeatures) -> None:
    """Register API routers; registration order is part of the routing contract."""
    app.include_router(ping.router, tags=["ping"])
    if features.database:
        _register_auth_routers(app)
    app.include_router(v1.router, tags=["api"])
    app.include_router(v2.router, tags=["api"])
    app.include_router(appwrite_route.router, tags=["appwrite"])
    app.include_router(tavily_route.router, tags=["search"])
    app.include_router(brave_route.router, tags=["search"])
    app.include_router(google_search_route.router, tags=["search"])
    app.include_router(integration.router, tags=["integration"])
    app.include_router(demo.router, tags=["integration"])
    if features.database:
        from nabla.api.notes import notes

        app.include_router(notes.router, tags=["notes"], dependencies=_DATABASE_REQUIRED)
    app.include_router(info.router, tags=["test"])
    if features.rag:
        from nabla.deepagents import workflow as ai_workflow

        app.include_router(ai_workflow.router, tags=["ai"])
    if features.mcp:
        from nabla.api import mcp_ops_route

        app.include_router(mcp_ops_route.router, tags=["mcp-ops"])
    app.include_router(keycloak.router, tags=["keycloak"])
    if features.database:
        from nabla.api import sensor, users

        app.include_router(users.router, tags=["users"], dependencies=_DATABASE_REQUIRED)
        # The sensor dashboard (also served at "/") runs from in-memory readings.
        app.include_router(sensor.router, tags=["sensor"])
    _register_optional_routers(app, debug=debug)


def _register_optional_routers(app: FastAPI, *, debug: bool) -> None:
    """Register environment-gated diagnostics, debug and websocket routes."""
    from nabla.utils.runtime_logs import runtime_diagnostics_enabled

    if runtime_diagnostics_enabled():
        from nabla.api import runtime_diagnostics

        app.include_router(runtime_diagnostics.router, tags=["runtime-devtools"])

    if debug:
        from fastapi_featureflags import router as ff_router

        app.include_router(ff_router, prefix="/ff", tags=["FeatureFlags"])

    from nabla.api.demo.socket.websocket import websocket_endpoint

    app.add_api_websocket_route("/ws/sensor", websocket_endpoint)


def _configure_mcp(app: FastAPI) -> None:
    """Expose MCP Streamable HTTP on the canonical /mcp endpoint."""
    from fastmcp import FastMCP
    from fastmcp.server.providers.openapi.routing import HTTPRoute, MCPType

    from nabla.config import MCP_ALLOWED_ROUTES
    from nabla.mcp.resources import register_fastapi_resources

    def filter_route(route: HTTPRoute, default_type: MCPType) -> MCPType | None:
        if (route.method, route.path) in MCP_ALLOWED_ROUTES:
            return None
        return MCPType.EXCLUDE

    mcp = FastMCP.from_fastapi(app=app, name="mcp", route_map_fn=filter_route)
    register_fastapi_resources(mcp)

    # FastMCP owns the complete `/mcp` transport path. Mounting an app whose
    # internal path is `/` below `/mcp` makes clients/proxies depend on slash
    # redirects. Open WebUI expects a canonical Streamable HTTP endpoint.
    # An exact route (not a root mount) keeps `/mcp` unchanged without
    # swallowing unknown paths or the low-priority `/api/assets` frontend.
    mcp_app = mcp.http_app(path="/mcp")
    app.router.routes.append(Route("/mcp", mcp_app))
    app.state.mcp = mcp
    app.state.mcp_app = mcp_app
    logger.info("MCP Streamable HTTP exposed at /mcp")

    if get_settings().a2a_enabled:
        try:
            from nabla.a2a_app import build_a2a_starlette_application

            app.mount("/a2a", build_a2a_starlette_application())
            logger.info("A2A JSON-RPC mounted at /a2a")
        except ImportError as exc:
            logger.warning("A2A mount skipped: %s", exc)


def _configure_admin_panel(app: FastAPI) -> None:
    """Configure the SQLAdmin panel backed by PostgreSQL."""
    from sqladmin import Admin

    from nabla.api.db.database import engine
    from nabla.api.users.models import UserAdmin

    # The admin panel is part of the local application baseline. Unleash must not
    # become a startup dependency merely to decide whether this view is registered.
    Admin(app, engine, title="Example: SQLAlchemy").add_view(UserAdmin)


def _configure_hot_reload(app: FastAPI, *, debug: bool) -> None:
    """Configure hot reload for development mode."""
    if debug:
        from nabla.dev_reload import router as dev_reload_router

        app.include_router(dev_reload_router)
        templates.env.globals["DEBUG"] = True


def _install_custom_openapi(app: FastAPI) -> None:
    """Install the cached custom OpenAPI schema generator."""

    def custom_openapi() -> dict[str, Any]:
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


def _configure_observability(app: FastAPI) -> None:
    """Configure request instrumentation, Logfire and Sentry."""
    from nabla.utils.logfire_config import configure_logfire
    from nabla.utils.sentry_config import configure_sentry

    configure_logfire(app, service_name=APP_NAME, service_version=APP_VERSION)
    configure_sentry()


def create_app(features: AppFeatures | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Without arguments every subsystem is enabled, which is the production
    contract exported by ``nabla.main.app``. Pass ``AppFeatures.minimal()`` (or
    a customised ``AppFeatures``) to omit PostgreSQL, Redis, observability, MCP
    or RAG wiring.
    """
    selected = features or AppFeatures()
    if selected.observability:
        from nabla.config_settings import DD_TRACE_ENABLED
        from nabla.utils.datadog_config import configure_datadog

        configure_datadog(enabled=DD_TRACE_ENABLED, app_name=APP_NAME)

    debug = application_debug_enabled(env_bool("DEBUG"))
    app = FastAPI(
        lifespan=_build_app_lifespan(selected),
        title=f"{APP_NAME} {APP_PREFIX_VERSION}",
        description="FastAPI Sample for demo",
        version=APP_RUNTIME_VERSION,
        debug=debug,
    )
    app.state.features = selected
    app.state.mcp = None
    app.state.mcp_app = None

    _install_custom_openapi(app)
    app.middleware("http")(logging_middleware)
    app.middleware("http")(metrics_middleware)
    app.middleware("http")(operations_access_middleware)
    configure_rate_limiting(app)
    _configure_unleash_middleware(app)
    if selected.observability:
        _configure_metrics(app)
    _register_routers(app, debug=debug, features=selected)
    if selected.database:
        _configure_admin_panel(app)
    _configure_hot_reload(app, debug=debug)
    if selected.observability:
        _configure_observability(app)
    register_routes(app, database=selected.database)
    if selected.mcp:
        _configure_mcp(app)
    return app


def create_minimal_app() -> FastAPI:
    """Create a local diagnostics app without DB/Redis/observability/MCP/RAG.

    Zero-argument entry point for ``uvicorn --factory``.
    """
    from nabla.utils.log_config import setup_logging

    setup_logging()
    return create_app(AppFeatures.minimal())
