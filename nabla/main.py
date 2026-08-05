# ruff: noqa: E402 -- Datadog opt-out environment must be set before SDK imports.
# pylint: disable=wrong-import-position

import argparse
import asyncio
import html
import os
import time
import warnings
from datetime import datetime
from typing import Any, Dict

# Datadog is a separate, explicit application opt-in. Force the SDK off before
# any application import unless DATADOG_ENABLED is deliberately enabled.
_DATADOG_ENABLED = os.environ.get("DATADOG_ENABLED", "false").lower() in {"1", "true", "yes"}
if not _DATADOG_ENABLED:
    os.environ["DD_TRACE_ENABLED"] = "false"
    os.environ["DD_LOGS_INJECTION"] = "false"
    os.environ["DD_PROFILING_ENABLED"] = "false"
    os.environ["DD_APPSEC_ENABLED"] = "false"
    os.environ["DD_IAST_ENABLED"] = "false"

import pybreaker
import pyroscope
import sentry_sdk
from ddtrace import config, patch, tracer
from ddtrace.contrib.trace_utils import set_user
from ddtrace.profiling import Profiler
from ddtrace.trace import TraceFilter
from fastapi import FastAPI, Request
from fastapi.concurrency import asynccontextmanager
from fastapi.openapi.utils import get_openapi
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    ORJSONResponse,
    RedirectResponse,
)
from fastapi.templating import Jinja2Templates
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_featureflags import router as ff_router
from fastmcp import FastMCP
from fastmcp.server.providers.openapi.routing import MCPType
from fastmcp.utilities.openapi.models import HTTPRoute

from prometheus_client import REGISTRY
from prometheus_client.openmetrics.exposition import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic.json_schema import PydanticJsonSchemaWarning
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqladmin import Admin
from sqlmodel import select
from starlette.middleware.cors import CORSMiddleware

from nabla.api import (
    appwrite_route,
    brave_route,
    google_search_route,
    mcp_ops_route,
    ping,
    tavily_route,
    v1,
    v2,
)
from nabla.api.auth import keycloak
from nabla.api.db.database import SessionLocal, database, engine, init_db
from nabla.api.demo import dd, demo, integration, sensor
from nabla.api.demo.models import init_db as init_db_sensor_reading
from nabla.api.demo.models import recent_readings
from nabla.api.demo.sensor import metrics
from nabla.api.demo.socket.redis import redis, start_event_listener
from nabla.api.demo.socket.websocket import websocket_endpoint
from nabla.api.health_checks import build_healthz_payload, build_sickz_payload
from nabla.api.notes import notes
from nabla.api.notes.models import Note
from nabla.api.notes.models import init_db as init_db_note
from nabla.api.test import info
from nabla.api.ui import render_api_root_page
from nabla.api.users import users
from nabla.api.users.models import UserAdmin, UserCreate, UserRead, UserUpdate
from nabla.api.users.models import init_db as init_db_user
from nabla.api.users.users import fastapi_users, jwt_backend
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
from nabla.utils.log_config import setup_logging
from nabla.utils.logger import logger
from nabla.utils.logfire_config import configure_logfire
from nabla.utils.prometheus import (
    INFLIGHT_REQUESTS,
    REQUESTS,
    REQUESTS_IN_PROGRESS,
    REQUESTS_PROCESSING_TIME,
    RESPONSES,
    PrometheusMiddleware,
    setting_otlp,
    update_system_metrics,
)
from nabla.utils.sentry_config import configure_sentry

# FastAPI / FastAPI-Users use Depends() as parameter defaults; OpenAPI generation
# emits PydanticJsonSchemaWarning (defaults are not JSON-schema-serializable).
warnings.filterwarnings(
    "ignore",
    category=PydanticJsonSchemaWarning,
    message=".*non-serializable-default.*",
)

# Disable Unleash integration if env variable is set to "false"
UNLEASH_ENABLED = os.getenv("UNLEASH_ENABLED", "False").lower() == "true"

_DD_PROFILING_ENABLED = DD_TRACE_ENABLED and os.environ.get("DD_PROFILING_ENABLED", "false").lower() in (
    "true",
    "1",
    "yes",
)
if _DD_PROFILING_ENABLED:
    prof = Profiler(
        env="prod",  # if not specified, falls back to environment variable DD_ENV
        service=APP_NAME,  # if not specified, falls back to environment variable DD_SERVICE
        # version="1.0.0",   # if not specified, falls back to environment variable DD_VERSION
    )
    prof.start()


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
    openapi_schema["info"]["x-logo"] = {
        "url": "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png",
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


setup_logging()

# logger = logging.getLogger(__name__)
# logger.level = logging.INFO

logger.info("Creating API")

# Setup rate limiter: 100 requests per minute per IP.
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

# Configure separate circuit breakers for the two external services:
# Both fail after 2 consecutive errors and open the circuit for 10 seconds.
circuit_breaker_web = pybreaker.CircuitBreaker(fail_max=2, reset_timeout=10)

if DD_TRACE_ENABLED:
    patch(fastapi=True)

    # Override service name
    config.fastapi["service_name"] = APP_NAME

# Override request span name
# config.fastapi["request_span_name"] = APP_NAME + "-request-span-name"

# Network sockets
# tracer.configure(
#    https=False,
#    hostname=DD_AGENT_HOST,
#    port=DD_TRACE_AGENT_PORT,
# )


class FilterbyName(TraceFilter):
    def process_trace(self, trace):
        for span in trace:
            if span.name == "get_quote":  # or assistant_helper
                # drop the full trace chunk
                return None
        return trace


if DD_TRACE_ENABLED:
    tracer.configure(trace_processors=[FilterbyName()])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """background task starts at startup"""

    FastAPICache.init(InMemoryBackend())

    app.state.redis = redis

    await database.connect()

    await init_db()  # create_db_and_tables()
    await init_db_note()
    await init_db_user()
    await init_db_sensor_reading()

    """Start background system monitoring"""
    system_metrics_task = asyncio.create_task(update_system_metrics())

    event_listener = asyncio.create_task(start_event_listener())

    logger.info("🚀 Sensor Dashboard application started successfully")
    logger.info(f"Debug mode: {bool(os.getenv('DEBUG'))}")
    logger.info(f"Initial sensor readings: {len(recent_readings)}")

    yield

    # Cancel the background task on shutdown
    system_metrics_task.cancel()
    event_listener.cancel()

    if database:
        await database.disconnect()

    # if app.state.redis:
    #     app.state.redis.close()

    logger.info("📊 Sensor Dashboard application shutting down")
    logger.info(
        f"Final metrics - Connections: {metrics.connection_count}, Requests: {metrics.total_requests}",
    )


# Combine both lifespans
@asynccontextmanager
async def combined_lifespan(app: FastAPI):
    # Run both lifespans
    async with lifespan(app):
        async with mcp_app.lifespan(app):
            yield


def _configure_unleash_feature_middleware(app: FastAPI) -> None:
    """Apply rate limit, logging, CORS, and Prometheus middleware per Unleash flags."""
    if not UNLEASH_ENABLED:
        logger.warning("UNLEASH integration is disabled via UNLEASH_ENABLED env variable.")

    if UNLEASH_ENABLED or client.is_enabled("rate_limiter"):
        app.add_exception_handler(
            RateLimitExceeded,
            lambda r, e: JSONResponse(
                status_code=429,
                content={"error": "Too Many Requests"},
            ),
        )
    else:
        logger.warning("Feature flag : rate_limiter is not enabled")

    if UNLEASH_ENABLED or client.is_enabled("cors"):
        origins = [
            "http://localhost",
            "http://localhost:8080",
            "http://localhost:8091",
            "http://localhost:8001",
            "https://fastapi-sample.service.gra.dev.consul/",
            "https://fastapi-sample.service.gra.uat.consul/",
            "https://fastapi-sample.fastapicloud.dev/",
        ]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=["*"],
        )
    else:
        logger.warning("Feature flag : cors is not enabled")

    if UNLEASH_ENABLED or client.is_enabled("logging_metrics"):
        # Setting metrics middleware
        # PrometheusMiddleware seems not working BUT below metrics_middleware works
        app.add_middleware(
            PrometheusMiddleware,
            app_name=APP_NAME,
        )
    else:
        logger.warning("Feature flag : logging_metrics is not enabled")


# def initialize_api() -> FastAPI:
def initialize_api(app, *, logfire_enabled: bool = False):
    """
    Initialize the API.

    :return: FastAPI
    :raise ValidationError: If there was an issue with the Settings
    """

    _configure_unleash_feature_middleware(app)

    api_settings = get_settings()

    if api_settings.metrics_enabled:
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

        # instrumentator.add(http_requested_languages_total())
        instrumentator.expose(app=app, include_in_schema=False)

    # Logfire owns the OpenTelemetry pipeline when enabled. Keep the legacy
    # exporter as an explicit fallback without installing two tracer providers.
    if not logfire_enabled and not OTEL_SDK_DISABLED and OTLP_GRPC_ENDPOINT:
        setting_otlp(app, APP_NAME, OTLP_GRPC_ENDPOINT)
    elif not logfire_enabled and not OTEL_SDK_DISABLED:
        logger.warning("OpenTelemetry enabled without OTLP_GRPC_ENDPOINT; exporter skipped")

    # Add prometheus asgi middleware to route /metrics requests
    # metrics_app = make_asgi_app()
    # app.mount("/metrics", metrics_app)

    # Note: do not mount ASGI app or append Mount route for /metrics - override via explicit route above

    app.include_router(
        ping.router,
        tags=["ping"],
        responses={404: {"description": "Not found"}},
    )

    app.include_router(fastapi_users.get_auth_router(jwt_backend), prefix="/auth/jwt", tags=["auth"])
    app.include_router(
        fastapi_users.get_register_router(UserRead, UserCreate),
        prefix="/auth",
        tags=["auth"],
    )
    app.include_router(
        fastapi_users.get_reset_password_router(),
        prefix="/auth",
        tags=["auth"],
    )
    app.include_router(
        fastapi_users.get_verify_router(UserRead),
        prefix="/auth",
        tags=["auth"],
    )
    app.include_router(
        fastapi_users.get_users_router(UserRead, UserUpdate),
        prefix="/users",
        tags=["users"],
    )

    app.include_router(v1.router, tags=["api"])
    app.include_router(v2.router, tags=["api"])
    app.include_router(appwrite_route.router, tags=["appwrite"])
    app.include_router(tavily_route.router, tags=["tavily"])
    app.include_router(brave_route.router, tags=["brave"])
    app.include_router(google_search_route.router, tags=["google"])
    app.include_router(integration.router, tags=["integration"])
    app.include_router(dd.router, tags=["integration"])
    app.include_router(demo.router, tags=["integration"])
    app.include_router(notes.router, tags=["notes"])
    app.include_router(info.router, tags=["test"])
    app.include_router(ai_workflow.router, tags=["ai"])
    app.include_router(mcp_ops_route.router, tags=["mcp-ops"])
    app.include_router(keycloak.router, tags=["keycloak"])
    app.include_router(users.router, tags=["users"])
    app.include_router(sensor.router, tags=["sensor"])

    if os.getenv("DEBUG"):
        app.include_router(ff_router, prefix="/ff", tags=["FeatureFlags"])

    app.add_api_websocket_route("/ws/sensor", websocket_endpoint)

    if not UNLEASH_ENABLED or client.is_enabled("admin_panel"):
        # Create admin
        admin = Admin(app, engine, title="Example: SQLAlchemy")

        # Add view
        # admin.add_view(ModelView(User))
        admin.add_view(UserAdmin)

    # return app


app = FastAPI(
    lifespan=combined_lifespan,
    title=APP_NAME + " " + APP_PREFIX_VERSION,
    description="FastAPI Sample for demo",
    version=APP_RUNTIME_VERSION,
    debug=os.getenv("DEBUG", "False").lower() == "true",
    default_response_class=ORJSONResponse,
)

initialize_api(
    app,
    logfire_enabled=configure_logfire(
        app,
        service_name=APP_NAME,
        service_version=APP_VERSION,
    ),
)

_MCP_ALLOWED_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/v1/tavily/search"),
        ("POST", "/v1/brave/search"),
        ("POST", "/v1/google/search"),
        ("GET", "/v2/version"),
        ("GET", "/demo/greet_user/{name}"),
        ("GET", "/demo/get_time"),
        ("GET", "/demo/add"),
        ("GET", "/demo/multiply"),
        # ("GET", "/test/users/current"),
        # ("GET", "/test/users/{user_id}"),
    },
)


def _mcp_openapi_route_filter(route: HTTPRoute, default_type: MCPType) -> MCPType | None:
    if (route.method, route.path) in _MCP_ALLOWED_ROUTES:
        return None
    return MCPType.EXCLUDE


# Convert to MCP server, see https://gofastmcp.com/integrations/fastapi
mcp = FastMCP.from_fastapi(
    app=app,
    name="mcp",
    route_map_fn=_mcp_openapi_route_filter,
)

# 2. Create the MCP's ASGI app
mcp_app = mcp.http_app(path="/mcp")

if not UNLEASH_ENABLED or client.is_enabled("mcp"):
    app.mount("/llm", mcp_app)
    # Now you have:
    # - Regular API: http://localhost:8091/v2/version
    # - LLM-friendly MCP: http://localhost:8091/llm/mcp/
    # Both served from the same FastAPI application!
elif not UNLEASH_ENABLED:
    logger.warning("MCP feature not enabled because UNLEASH_ENABLED is set.")
else:
    logger.warning("Feature flag : mcp is not enabled")

if get_settings().a2a_enabled:
    try:
        from nabla.a2a_app import build_a2a_starlette_application

        app.mount("/a2a", build_a2a_starlette_application())
        logger.info("A2A JSON-RPC mounted at /a2a (agent card: /a2a/.well-known/agent-card.json)")
    except ImportError as exc:
        logger.warning("A2A mount skipped (a2a-sdk not installed): %s", exc)


@app.middleware("http")
async def metrics_middleware(request, call_next):
    """
    🔧 Automatic metrics collection middleware
    This captures every request without modifying your business logic
    """
    start_time = time.time()
    INFLIGHT_REQUESTS.inc()
    REQUESTS_IN_PROGRESS.labels(
        method=request.method,
        path=request.url.path,
        app_name=APP_NAME,
    ).inc()
    REQUESTS.labels(
        method=request.method,
        path=request.url.path,
        app_name=APP_NAME,
    ).inc()
    try:
        response = await call_next(request)
        RESPONSES.labels(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            app_name=APP_NAME,
        ).inc()
        REQUESTS_PROCESSING_TIME.labels(
            method=request.method,
            path=request.url.path,
            app_name=APP_NAME,
        ).observe(time.time() - start_time)
        return response
    finally:
        INFLIGHT_REQUESTS.dec()
        REQUESTS_IN_PROGRESS.labels(
            method=request.method,
            path=request.url.path,
            app_name=APP_NAME,
        ).dec()


@app.middleware("http")
async def logging_middleware(request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed",
            method=request.method,
            path=request.url.path,
            duration_seconds=time.time() - start_time,
        )
        raise

    duration = time.time() - start_time
    log_fields = {
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_seconds": duration,
    }
    noisy_success_paths = {
        "/docs",
        "/docs/oauth2-redirect",
        "/health",
        "/healthz",
        "/logs",
        "/metrics",
        "/openapi.json",
        "/ping",
        "/redoc",
        "/sickz",
        "/stream",
    }
    noisy_success_prefixes = (
        "/llm/",
        "/logs/",
        "/stream/",
        "/v1/mcp/",
    )
    is_noisy_success = response.status_code < 400 and (
        request.url.path in noisy_success_paths
        or request.url.path.startswith(noisy_success_prefixes)
    )

    if response.status_code >= 500:
        logger.error("request_completed", **log_fields)
    elif response.status_code >= 400 or duration >= 2.0:
        logger.warning("request_completed", **log_fields)
    elif not is_noisy_success:
        logger.info("request_completed", **log_fields)
    return response


# See https://docs.datadoghq.com/fr/security/application_security/threats/add-user-info/?tab=python
user_id = "usr.id"
set_user(
    tracer,
    user_id,
    name="AlbanAndrieu",
    email=os.environ.get("MAIL_FROM", "alban.andrieu@gmail.com"),
    scope="sample_scope",
    role="manager",
    session_id="id_session",
    propagate=True,
)


configure_sentry()

templates = Jinja2Templates(directory="templates")


async def reload_data():
    print("Reloading server data...")


# Hot reload magic for development (because restarting servers is for losers)
# arel is optional: only imported when DEBUG is set so Cloudflare Workers (no arel in Pyodide) can deploy.
if os.getenv("DEBUG"):
    import arel

    # hot_reload = arel.HotReload(paths=["."])
    hot_reload = arel.HotReload(
        paths=[
            arel.Path("./nabla/data", on_reload=[reload_data]),
            arel.Path("./nabla/static"),
            arel.Path("./templates"),
        ],
    )
    app.add_websocket_route("/hot-reload", route=hot_reload)
    app.add_event_handler("startup", hot_reload.startup)
    app.add_event_handler("shutdown", hot_reload.shutdown)
    templates.env.globals["DEBUG"] = True
    templates.env.globals["hot_reload"] = hot_reload


# See https://boadziedaniel.medium.com/building-real-time-dashboards-with-fastapi-and-htmx-01ea458673cb
@app.get("/", response_class=HTMLResponse)
# TODO @circuit_breaker_web
@limiter.limit("100/second")
def dashboard(request: Request):
    session = SessionLocal()
    notes = session.exec(select(Note)).all()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "notes": notes},
    )


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    # /vercel.svg is automatically served when included in the public/** directory.
    return RedirectResponse("/vercel.svg", status_code=307)


# Define a resource
@mcp.resource("config://settings")
def get_settings() -> str:
    """Get server configuration settings."""
    return "Server Configuration: Version " + APP_VERSION


@app.get("/api/data")
def get_sample_data():
    return {
        "data": [
            {"id": 1, "name": "Sample Item 1", "value": 100},
            {"id": 2, "name": "Sample Item 2", "value": 200},
            {"id": 3, "name": "Sample Item 3", "value": 300},
        ],
        "total": 3,
        "timestamp": "2024-01-01T00:00:00Z",
    }


@app.get("/api/items/{item_id}")
def get_item(item_id: int):
    return {
        "item": {
            "id": item_id,
            "name": "Sample Item " + str(item_id),
            "value": item_id * 100,
        },
        "timestamp": "2024-01-01T00:00:00Z",
    }


@app.get("/api", response_class=HTMLResponse)
def read_root(request: Request):
    return render_api_root_page(
        title_suffix=os.getenv("TITLE_SUFFIX"),
        app_version=html.escape(str(request.app.version)),
    )


@app.get(
    "/healthz",
    response_class=ORJSONResponse,
    tags=["Health"],
    summary="Deep healthcheck",
)
async def get_healthz(request: Request) -> Dict[str, Any]:
    """Return JSON: ``GET /health`` payload merged with Redis, Postgres, Supabase, OVH ``/me``, etc."""
    with pyroscope.tag_wrapper({"function": "fast"}):
        return await build_healthz_payload(request, redis_client=redis, engine=engine)


@app.get(
    "/sickz",
    response_class=ORJSONResponse,
    tags=["Health"],
    summary="Inverse reachability (sickz)",
)
async def get_sickz(request: Request) -> Dict[str, Any]:
    """Return JSON: URL groups in ``SICKZ_TARGETS`` must not be reachable (unless ``SICKZ_INTERNAL_NETWORK``)."""
    with pyroscope.tag_wrapper({"function": "fast"}):
        return await build_sickz_payload(request)


@app.get("/sentry-debug", response_class=JSONResponse)
async def trigger_error() -> JSONResponse:
    """Send a controlled test error to Sentry without polluting ASGI logs."""
    event_id = None
    try:
        _ = 1 / 0
    except ZeroDivisionError as exc:
        event_id = sentry_sdk.capture_exception(exc)

    return JSONResponse(
        status_code=500,
        content={
            "error": "Intentional Sentry test error",
            "event_id": str(event_id) if event_id else None,
        },
    )


# Error handling
@app.exception_handler(Exception)
def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.opt(exception=exc).error("Unhandled exception on {}", request.url)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "timestamp": datetime.now().isoformat()},
    )


parser = argparse.ArgumentParser(prog="nabla")
parser.add_argument("echo", help="String to print back to the console")


@app.get("/metrics")
def prometheus_metrics():
    if os.environ.get("ENV") == "dev":
        return Response(generate_latest(REGISTRY), media_type="text/plain")
    else:
        return Response(generate_latest(REGISTRY), headers={"Content-Type": CONTENT_TYPE_LATEST})


def main():
    args = parser.parse_args()
    print(args.echo)
