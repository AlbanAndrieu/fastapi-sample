import argparse
import asyncio
import html
import logging
import os
import re
import time
import warnings
from datetime import datetime
from typing import Any, Dict

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
from prometheus_client import make_asgi_app
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic.json_schema import PydanticJsonSchemaWarning
from sentry_sdk.integrations.logging import LoggingIntegration
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqladmin import Admin
from sqlmodel import select
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount

from nabla.ai import workflow as ai_workflow
from nabla.api import appwrite_route, brave_route, google_search_route, ping, tavily_route, v1, v2
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
from nabla.api.users import users
from nabla.api.users.models import UserAdmin, UserCreate, UserRead, UserUpdate
from nabla.api.users.models import init_db as init_db_user
from nabla.api.users.users import fastapi_users, jwt_backend
from nabla.config_settings import (
    APP_NAME,
    APP_PREFIX_VERSION,
    APP_VERSION,
    OTLP_GRPC_ENDPOINT,
    SENTRY_DSN,
    client,
    get_settings,
)
from nabla.utils.log_config import LogMiddleware, setup_logging
from nabla.utils.logger import logger
from nabla.utils.sentry_filters import before_send_filter_test_noise
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

# FastAPI / FastAPI-Users use Depends() as parameter defaults; OpenAPI generation
# emits PydanticJsonSchemaWarning (defaults are not JSON-schema-serializable).
warnings.filterwarnings(
    "ignore",
    category=PydanticJsonSchemaWarning,
    message=".*non-serializable-default.*",
)

# Disable Unleash integration if env variable is set to "false"
UNLEASH_ENABLED = os.getenv("UNLEASH_ENABLED", "False").lower() == "true"

_DD_PROFILING_ENABLED = os.environ.get("DD_PROFILING_ENABLED", "false").lower() in (
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

    if UNLEASH_ENABLED or client.is_enabled("logging_requests"):
        app.add_middleware(LogMiddleware)

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
def initialize_api(app):
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

    # Setting OpenTelemetry exporter
    setting_otlp(app, APP_NAME, OTLP_GRPC_ENDPOINT)

    # Add prometheus asgi middleware to route /metrics requests
    # metrics_app = make_asgi_app()
    # app.mount("/metrics", metrics_app)

    # Add prometheus asgi middleware to route /metrics requests
    # https://github.com/prometheus/client_python/issues/1016
    route = Mount("/metrics", make_asgi_app())
    route.path_regex = re.compile("^/metrics(?P<path>.*)$")
    app.routes.append(route)

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
    version=f"{APP_PREFIX_VERSION}{APP_VERSION}",
    debug=os.getenv("DEBUG", "False").lower() == "true",
    default_response_class=ORJSONResponse,
)

initialize_api(app)

_MCP_ALLOWED_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/test/users/current"),
        ("GET", "/test/users/{user_id}"),
        ("POST", "/v1/tavily/search"),
        ("POST", "/v1/brave/search"),
        ("POST", "/v1/google/search"),
        ("GET", "/v2/version"),
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
    response = await call_next(request)

    logger.info(
        "request_completed",
        method=request.method,
        url=str(request.url),
        status_code=response.status_code,
        duration=time.time() - start_time,
    )
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

sentry_sdk.init(
    dsn=SENTRY_DSN,
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    # We recommend adjusting this value in production,
    traces_sample_rate=1.0,
    # Set profiles_sample_rate to 1.0 to profile 100%
    # of sampled transactions.
    # We recommend adjusting this value in production.
    profiles_sample_rate=1.0,
    integrations=[
        LoggingIntegration(
            level=logging.INFO,  # Capture info and above as breadcrumbs
            event_level=logging.ERROR,  # Send errors as events
        ),
    ],
    before_send=before_send_filter_test_noise,
)

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
    TITLE_SUFFIX = os.getenv("TITLE_SUFFIX")
    app_version = html.escape(str(request.app.version))
    return (
        """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Vercel + FastAPI : """
        + str(TITLE_SUFFIX)
        + """ </title>
        <link rel="icon" type="image/x-icon" href="/favicon.ico">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', sans-serif;
                background-color: #000000;
                color: #ffffff;
                line-height: 1.6;
                min-height: 100vh;
                display: flex;
                flex-direction: column;
            }

            header {
                border-bottom: 1px solid #333333;
                padding: 0;
            }

            nav {
                max-width: 1200px;
                margin: 0 auto;
                display: flex;
                align-items: center;
                padding: 1rem 2rem;
                gap: 2rem;
            }

            .logo {
                font-size: 1.25rem;
                font-weight: 600;
                color: #ffffff;
                text-decoration: none;
            }

            .nav-links {
                display: flex;
                gap: 1.5rem;
                margin-left: auto;
            }

            .nav-links a {
                text-decoration: none;
                color: #888888;
                padding: 0.5rem 1rem;
                border-radius: 6px;
                transition: all 0.2s ease;
                font-size: 0.875rem;
                font-weight: 500;
            }

            .nav-links a:hover {
                color: #ffffff;
                background-color: #111111;
            }

            main {
                flex: 1;
                max-width: 1200px;
                margin: 0 auto;
                padding: 4rem 2rem;
                display: flex;
                flex-direction: column;
                align-items: center;
                text-align: center;
            }

            .hero {
                margin-bottom: 3rem;
            }

            .hero-code {
                margin-top: 2rem;
                width: 100%;
                max-width: 900px;
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            }

            .hero-code pre {
                background-color: #0a0a0a;
                border: 1px solid #333333;
                border-radius: 8px;
                padding: 1.5rem;
                text-align: left;
                grid-column: 1 / -1;
            }

            h1 {
                font-size: 3rem;
                font-weight: 700;
                margin-bottom: 1rem;
                background: linear-gradient(to right, #ffffff, #888888);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }

            .subtitle {
                font-size: 1.25rem;
                color: #888888;
                margin-bottom: 2rem;
                max-width: 600px;
            }

            .cards {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 1.5rem;
                width: 100%;
                max-width: 900px;
            }

            .card {
                background-color: #111111;
                border: 1px solid #333333;
                border-radius: 8px;
                padding: 1.5rem;
                transition: all 0.2s ease;
                text-align: left;
            }

            .card:hover {
                border-color: #555555;
                transform: translateY(-2px);
            }

            .card h3 {
                font-size: 1.125rem;
                font-weight: 600;
                margin-bottom: 0.5rem;
                color: #ffffff;
            }

            .card p {
                color: #888888;
                font-size: 0.875rem;
                margin-bottom: 1rem;
            }

            .card a {
                display: inline-flex;
                align-items: center;
                color: #ffffff;
                text-decoration: none;
                font-size: 0.875rem;
                font-weight: 500;
                padding: 0.5rem 1rem;
                background-color: #222222;
                border-radius: 6px;
                border: 1px solid #333333;
                transition: all 0.2s ease;
            }

            .card a:hover {
                background-color: #333333;
                border-color: #555555;
            }

            .status-badge {
                display: inline-flex;
                align-items: center;
                gap: 0.5rem;
                background-color: #0070f3;
                color: #ffffff;
                padding: 0.25rem 0.75rem;
                border-radius: 20px;
                font-size: 0.75rem;
                font-weight: 500;
                margin-bottom: 2rem;
            }

            .status-dot {
                width: 6px;
                height: 6px;
                background-color: #00ff88;
                border-radius: 50%;
            }

            pre {
                background-color: #0a0a0a;
                border: 1px solid #333333;
                border-radius: 6px;
                padding: 1rem;
                overflow-x: auto;
                margin: 0;
            }

            code {
                font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, 'Courier New', monospace;
                font-size: 0.85rem;
                line-height: 1.5;
                color: #ffffff;
            }

            /* Syntax highlighting */
            .keyword {
                color: #ff79c6;
            }

            .string {
                color: #f1fa8c;
            }

            .function {
                color: #50fa7b;
            }

            .class {
                color: #8be9fd;
            }

            .module {
                color: #8be9fd;
            }

            .variable {
                color: #f8f8f2;
            }

            .decorator {
                color: #ffb86c;
            }

            .health-board {
                width: 100%;
                max-width: 900px;
                margin: 0 auto 3rem;
                text-align: left;
                background-color: #111111;
                border: 1px solid #333333;
                border-radius: 12px;
                padding: 1.5rem 1.75rem;
            }

            .health-board-title {
                font-size: 1.25rem;
                font-weight: 600;
                color: #ffffff;
                margin-bottom: 0.35rem;
            }

            .health-board-meta {
                font-size: 0.8rem;
                color: #888888;
                margin-bottom: 1rem;
            }

            .health-board-meta a {
                color: #7ab8ff;
            }

            .health-subboard-title {
                font-size: 1.1rem;
                font-weight: 600;
                margin: 2rem 0 0.35rem;
                color: #e8e8e8;
            }

            .health-refresh {
                margin-left: 0.75rem;
                padding: 0.25rem 0.65rem;
                font-size: 0.75rem;
                border-radius: 6px;
                border: 1px solid #444444;
                background: #1a1a1a;
                color: #e0e0e0;
                cursor: pointer;
            }

            .health-refresh:hover {
                border-color: #666666;
                color: #ffffff;
            }

            .health-summary {
                display: flex;
                align-items: center;
                gap: 0.65rem;
                padding: 0.65rem 1rem;
                border-radius: 8px;
                font-size: 0.9rem;
                font-weight: 500;
                margin-bottom: 1rem;
                border: 1px solid #333333;
            }

            .health-summary--green {
                background: rgba(0, 255, 136, 0.08);
                border-color: rgba(0, 255, 136, 0.35);
                color: #7dffc4;
            }

            .health-summary--yellow {
                background: rgba(255, 200, 50, 0.08);
                border-color: rgba(255, 200, 50, 0.4);
                color: #ffd966;
            }

            .health-summary--red {
                background: rgba(255, 80, 80, 0.1);
                border-color: rgba(255, 80, 80, 0.45);
                color: #ff9999;
            }

            .health-summary--neutral {
                background: #0a0a0a;
                color: #aaaaaa;
            }

            .health-led {
                width: 12px;
                height: 12px;
                border-radius: 50%;
                flex-shrink: 0;
                box-shadow: 0 0 10px currentColor;
            }

            .health-led--green { background: #00ff88; color: #00ff88; }
            .health-led--yellow { background: #ffcc33; color: #ffcc33; }
            .health-led--red { background: #ff4444; color: #ff4444; }
            .health-led--gray { background: #555555; color: #555555; box-shadow: none; }

            .health-checks {
                list-style: none;
                margin: 0;
                padding: 0;
                display: flex;
                flex-direction: column;
                gap: 0.5rem;
            }

            .health-row {
                display: flex;
                align-items: flex-start;
                gap: 0.75rem;
                padding: 0.55rem 0.65rem;
                background: #0a0a0a;
                border-radius: 8px;
                border: 1px solid #2a2a2a;
            }

            .health-row-icon {
                flex-shrink: 0;
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 10px;
                border-width: 1px;
                border-style: solid;
            }

            .health-row-icon svg {
                width: 22px;
                height: 22px;
            }

            .health-row-icon--img img {
                width: 26px;
                height: 26px;
                object-fit: contain;
                display: block;
            }

            .health-row-icon--green {
                color: #00ff88;
                background: rgba(0, 255, 136, 0.08);
                border-color: rgba(0, 255, 136, 0.35);
                box-shadow: 0 0 12px rgba(0, 255, 136, 0.15);
            }

            .health-row-icon--yellow {
                color: #ffcc33;
                background: rgba(255, 204, 51, 0.08);
                border-color: rgba(255, 204, 51, 0.4);
                box-shadow: 0 0 12px rgba(255, 204, 51, 0.12);
            }

            .health-row-icon--red {
                color: #ff4444;
                background: rgba(255, 68, 68, 0.1);
                border-color: rgba(255, 68, 68, 0.45);
                box-shadow: 0 0 12px rgba(255, 68, 68, 0.12);
            }

            .health-row-icon--gray {
                color: #888888;
                background: #141414;
                border-color: #2a2a2a;
                box-shadow: none;
            }

            .health-row-led-wrap {
                flex-shrink: 0;
                padding-top: 0.35rem;
            }

            .health-row-main {
                flex: 1;
                min-width: 0;
            }

            .health-row-primary {
                min-width: 0;
            }

            .health-row-primary--green .health-row-name,
            .health-row-primary--green .health-row-detail {
                color: #00ff88;
            }

            .health-row-primary--green .health-row-name .sickz-target-link {
                color: #00ff88;
                text-decoration-color: rgba(0, 255, 136, 0.45);
            }

            .health-row-primary--green .health-row-name .sickz-target-link:hover {
                color: #66ffc4;
                text-decoration-color: rgba(102, 255, 196, 0.65);
            }

            .health-row-primary--yellow .health-row-name,
            .health-row-primary--yellow .health-row-detail {
                color: #ffcc33;
            }

            .health-row-primary--yellow .health-row-name .sickz-target-link {
                color: #ffcc33;
                text-decoration-color: rgba(255, 204, 51, 0.45);
            }

            .health-row-primary--yellow .health-row-name .sickz-target-link:hover {
                color: #ffe066;
                text-decoration-color: rgba(255, 224, 102, 0.65);
            }

            .health-row-primary--red .health-row-name,
            .health-row-primary--red .health-row-detail {
                color: #ff6666;
            }

            .health-row-primary--red .health-row-name .sickz-target-link {
                color: #ff6666;
                text-decoration-color: rgba(255, 102, 102, 0.5);
            }

            .health-row-primary--red .health-row-name .sickz-target-link:hover {
                color: #ff9999;
                text-decoration-color: rgba(255, 153, 153, 0.65);
            }

            .health-row-primary--gray .health-row-name,
            .health-row-primary--gray .health-row-detail {
                color: #9ca3af;
            }

            .health-row-primary--gray .health-row-name .sickz-target-link {
                color: #9ca3af;
                text-decoration-color: rgba(156, 163, 175, 0.45);
            }

            .health-row-primary--gray .health-row-name .sickz-target-link:hover {
                color: #cbd5e1;
                text-decoration-color: rgba(203, 213, 225, 0.55);
            }

            .health-row-name {
                font-weight: 600;
                font-size: 0.875rem;
                color: #f0f0f0;
            }

            .health-row-detail {
                font-size: 0.75rem;
                color: #888888;
                margin-top: 0.2rem;
                word-break: break-word;
            }

            .health-row-tags {
                font-size: 0.65rem;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: #666666;
                margin-top: 0.25rem;
            }

            .health-row-name--sickz {
                display: flex;
                align-items: center;
                gap: 0.4rem;
                flex-wrap: wrap;
            }

            .sickz-lock-wrap {
                display: inline-flex;
                align-items: center;
                flex-shrink: 0;
            }

            .sickz-lock-svg {
                width: 14px;
                height: 14px;
                display: block;
            }

            .sickz-lock--trusted {
                color: #00ff88;
            }

            .sickz-lock--untrusted {
                color: #ff4444;
            }

            .sickz-lock--unknown {
                color: #888888;
            }

            .sickz-target-link {
                color: #f0f0f0;
                text-decoration: underline;
                text-decoration-color: rgba(240, 240, 240, 0.35);
            }

            .sickz-target-link:hover {
                color: #ffffff;
                text-decoration-color: rgba(0, 255, 136, 0.55);
            }

            .health-error {
                color: #ff8888;
                font-size: 0.75rem;
                margin-top: 0.35rem;
            }

            @media (max-width: 768px) {
                nav {
                    padding: 1rem;
                    flex-direction: column;
                    gap: 1rem;
                }

                .nav-links {
                    margin-left: 0;
                }

                main {
                    padding: 2rem 1rem;
                }

                h1 {
                    font-size: 2rem;
                }

                .hero-code {
                    grid-template-columns: 1fr;
                }

                .cards {
                    grid-template-columns: 1fr;
                }
            }
        </style>
    </head>
    <body>
        <header>
            <nav>
                <a href="/" class="logo">Vercel + FastAPI : """
        + str(TITLE_SUFFIX)
        + """</a>
                <div class="nav-links">
                    <a href="/docs">API Docs</a>
                    <a href="/api/data">API</a>
                    <a href="#health-board">Health</a>
                </div>
            </nav>
        </header>
        <main>
            <div class="hero">
                <h1>Vercel + FastAPI : """
        + str(TITLE_SUFFIX)
        + """</h1>
                <p class="subtitle" style="margin-top: -0.5rem;">App version : <strong>"""
        + app_version
        + """</strong></p>
                <div class="hero-code">
                    <pre><code><span class="keyword">from</span> <span class="module">fastapi</span> <span class="keyword">import</span> <span class="class">FastAPI</span>

<span class="variable">app</span> = <span class="class">FastAPI</span>()

<span class="decorator">@app.get</span>(<span class="string">"/"</span>)
<span class="keyword">def</span> <span class="function">read_root</span>():
    <span class="keyword">return</span> {<span class="string">"Python"</span>: <span class="string">"on Vercel"</span>}</code></pre>
                </div>
            </div>

            <section class="health-board" id="health-board" aria-labelledby="health-board-title">
                <h2 class="health-board-title" id="health-board-title">Service health</h2>
                <p class="health-board-meta">Live view of <a href="/healthz">/healthz</a> and
                    <a href="/sickz">/sickz</a>.
                    <button type="button" class="health-refresh" id="health-refresh">Refresh</button>
                </p>
                <div class="health-summary health-summary--neutral" id="health-summary">
                    <span class="health-led health-led--gray" id="health-summary-led" aria-hidden="true"></span>
                    <span id="health-summary-text">Loading health checks…</span>
                </div>
                <ul class="health-checks" id="health-checks"></ul>
                <p class="health-error" id="health-fetch-error" hidden></p>

                <h3 class="health-subboard-title" id="sickz-board-title">Unreachable targets (sickz)</h3>
                <p class="health-board-meta">These URLs must <strong>not</strong> respond when this app runs
                    outside your home LAN. Probes are skipped when <code>SICKZ_INTERNAL_NETWORK=true</code>, or
                    implicitly when <code>SICKZ_NETWORK_LABEL=nabla</code> or
                    <code>APP_DOMAIN=albandrieu.albandrieu.com</code> (unless a cloud/PaaS runtime is detected).
                    <code>SICKZ_NETWORK_LABEL</code> / <code>APP_DOMAIN</code> also name the network in messages.
                    Separate equivalent URLs with <code>|</code>; separate unrelated targets with commas.
                    Probes use TLS verify off so certificate issues do not hide reachability.</p>
                <div class="health-summary health-summary--neutral" id="sickz-summary">
                    <span class="health-led health-led--gray" id="sickz-summary-led" aria-hidden="true"></span>
                    <span id="sickz-summary-text">Loading sickz checks…</span>
                </div>
                <p class="health-board-meta" id="sickz-lan-hint" hidden style="margin-top: 0.35rem"></p>
                <ul class="health-checks" id="sickz-checks"></ul>
                <p class="health-error" id="sickz-fetch-error" hidden></p>
            </section>

            <div class="cards">
                <div class="card">
                    <h3>Interactive API Docs</h3>
                    <p>Explore this API's endpoints with the interactive Swagger UI. Test requests and view response schemas in real-time.</p>
                    <a href="/docs">Open Swagger UI →</a>
                </div>

                <div class="card">
                    <h3>Sample Data</h3>
                    <p>Access sample JSON data through our REST API. Perfect for testing and development purposes.</p>
                    <a href="/api/data">Get Data →</a>
                </div>

            </div>
        </main>
    <script>
    (function () {
        const LABELS = {
            redis: "Redis",
            postgres: "PostgreSQL",
            supabase: "Supabase",
            openstack_me: "OVH / OpenStack API",
            tavily: "Tavily Search",
            brave: "Brave Search",
            google: "Google Programmable Search",
            appwrite: "Appwrite",
            keycloak: "Keycloak (OpenID)",
            unleash: "Unleash",
            sentry: "Sentry",
            datadog: "Datadog Agent",
            pyroscope: "Pyroscope",
            litellm: "LiteLLM proxy",
            albandrieu_twofactor: "twofactor-auth",
            albandrieu_nexus: "nexus",
            albandrieu_keycloak_ui: "keycloak",
            albandrieu_homarr: "homarr",
            albandrieu_plumber_api: "plumber-api",
            albandrieu_reactive_resume: "reactive-resume",
            albandrieu_vaultwarden: "vaultwarden-albandrieu",
        };
        const MANDATORY = new Set([
            "postgres",
            "redis",
            "supabase",
            "albandrieu_twofactor",
            "albandrieu_nexus",
            "albandrieu_keycloak_ui",
            "albandrieu_homarr",
            "albandrieu_plumber_api",
            "albandrieu_reactive_resume",
            "albandrieu_vaultwarden",
        ]);

        /* Filenames from https://selfh.st/icons/ (selfhst/icons repo, default SVG variant). */
        const SELFHST_ICON_CDN =
            "https://cdn.jsdelivr.net/gh/selfhst/icons@main/svg/";
        const HEALTHZ_ICON_IMG = {
            postgres: "postgresql.svg",
            redis: "redis.svg",
            supabase: "supabase.svg",
            openstack_me: "ovh.svg",
            tavily: "searxng.svg",
            brave: "brave.svg",
            google: "google.svg",
            appwrite: "appwrite.svg",
            keycloak: "keycloak.svg",
            sentry: "sentry.svg",
            datadog: "datadog.svg",
            pyroscope: "grafana.svg",
            litellm: "litellm.svg",
            albandrieu_twofactor: "2fauth.svg",
            albandrieu_nexus: "sonatype-nexus-repository.svg",
            albandrieu_keycloak_ui: "keycloak.svg",
            albandrieu_homarr: "homarr.svg",
            albandrieu_plumber_api: "docker.svg",
            albandrieu_reactive_resume: "reactive-resume.svg",
            albandrieu_vaultwarden: "vaultwarden.svg",
            sickz_url: "pfsense.svg",
        };

        const ICON_PATHS = {
            unleash:
                '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" x2="4" y1="22" y2="15"/>',
            infra_host:
                '<circle cx="12" cy="12" r="9"/><path d="M8 12h8M12 8v8"/>',
            _default: '<rect x="5" y="5" width="14" height="14" rx="2"/><path d="M9 12h6M12 9v6"/>',
        };

        function serviceIconSvg(key, statusCls) {
            var imgFile = HEALTHZ_ICON_IMG[key];
            if (imgFile) {
                return (
                    '<span class="health-row-icon health-row-icon--img health-row-icon--' +
                    statusCls +
                    '" aria-hidden="true">' +
                    '<img src="' +
                    SELFHST_ICON_CDN +
                    imgFile +
                    '" alt="" width="26" height="26" loading="lazy" referrerpolicy="no-referrer" />' +
                    "</span>"
                );
            }
            var d =
                ICON_PATHS[key] ||
                (key.indexOf("albandrieu_") === 0 ? ICON_PATHS.infra_host : ICON_PATHS._default);
            return (
                '<span class="health-row-icon health-row-icon--' +
                statusCls +
                '" aria-hidden="true">' +
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
                d +
                "</svg></span>"
            );
        }

        function sickzEscapeText(s) {
            return String(s)
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;");
        }

        function sickzUrlForDetail(u) {
            return String(u).replace(/^https?:\\/\\//i, "");
        }

        function sickzShortHostForDetail(u) {
            var s = String(u).replace(/^https?:\\/\\//i, "");
            var slash = s.indexOf("/");
            if (slash !== -1) s = s.slice(0, slash);
            var lower = s.toLowerCase();
            var suff = ".albandrieu.com";
            if (lower.endsWith(suff)) return s.slice(0, -suff.length) || s;
            return s;
        }

        function sickzLockHtml(tlsTrusted, hrefRaw) {
            var h = (hrefRaw || "").trim().toLowerCase();
            var isHttps = h.indexOf("https:") === 0;
            var wrapCls;
            var label;
            if (!isHttps) {
                wrapCls = "sickz-lock--unknown";
                label = "TLS: not applicable (non-HTTPS or no link)";
            } else if (tlsTrusted === true) {
                wrapCls = "sickz-lock--trusted";
                label = "TLS: certificate validated";
            } else {
                wrapCls = "sickz-lock--untrusted";
                label =
                    tlsTrusted === false
                        ? "TLS: certificate not trusted"
                        : "TLS: not validated (unreachable or check incomplete)";
            }
            var lockPaths =
                '<rect x="5" y="11" width="14" height="10" rx="2" ry="2"/>' +
                '<path d="M7 11V7a5 5 0 0 1 10 0v4"/>';
            return (
                '<span class="sickz-lock-wrap ' +
                wrapCls +
                '" role="img" aria-label="' +
                sickzEscapeText(label) +
                '">' +
                '<svg class="sickz-lock-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">' +
                lockPaths +
                "</svg></span>"
            );
        }

        function sickzRowIcon(check, statusCls) {
            var fn = check.icon_filename;
            if (fn && typeof fn === "string") {
                return (
                    '<span class="health-row-icon health-row-icon--img health-row-icon--' +
                    statusCls +
                    '" aria-hidden="true">' +
                    '<img src="' +
                    SELFHST_ICON_CDN +
                    sickzEscapeText(fn) +
                    '" alt="" width="26" height="26" loading="lazy" referrerpolicy="no-referrer" />' +
                    "</span>"
                );
            }
            return serviceIconSvg("sickz_url", statusCls);
        }

        function healthRowTitleHtml(check, key) {
            var rowTitle =
                check.display_label != null ? check.display_label : LABELS[key] ? LABELS[key] : key;
            rowTitle = String(rowTitle);
            var hrefRaw = (check.href || "").trim();
            var lock = sickzLockHtml(check.tls_trusted, hrefRaw);
            var inner =
                hrefRaw.length > 0
                    ? '<a class="sickz-target-link" target="_blank" rel="noopener noreferrer" href="' +
                      sickzEscapeText(hrefRaw) +
                      '">' +
                      sickzEscapeText(rowTitle) +
                      "</a>"
                    : "<span>" + sickzEscapeText(rowTitle) + "</span>";
            return '<div class="health-row-name health-row-name--sickz">' + lock + inner + "</div>";
        }

        function classify(check) {
            if (check.skipped === true) return "yellow";
            if (check.reachable === true) return "green";
            if (check.reachable === false) return "red";
            return "gray";
        }

        function mandatoryFailed(key, check) {
            if (!MANDATORY.has(key)) return false;
            if (check.skipped === true) return false;
            return check.reachable === false;
        }

        function detailText(check) {
            if (check.skipped) return check.reason || "Not configured (intentionally disabled).";
            if (check.reachable === true) {
                const parts = [];
                if (check.http_status != null) parts.push("HTTP " + check.http_status);
                if (check.path) parts.push(check.path);
                if (check.host != null && check.port != null) parts.push(check.host + ":" + check.port);
                if (check.url) parts.push(String(check.url).replace(/^https?:\\/\\//i, ""));
                return parts.length ? parts.join(" · ") : "Connected.";
            }
            if (check.error) return check.error;
            return "Unreachable.";
        }

        function sortKeys(keys) {
            const first = [
                "postgres",
                "redis",
                "supabase",
                "albandrieu_twofactor",
                "albandrieu_nexus",
                "albandrieu_keycloak_ui",
                "albandrieu_homarr",
                "albandrieu_plumber_api",
                "albandrieu_reactive_resume",
                "albandrieu_vaultwarden",
                "litellm",
            ];
            const rest = keys.filter(function (k) { return first.indexOf(k) === -1; }).sort();
            return first.filter(function (k) { return keys.indexOf(k) !== -1; }).concat(rest);
        }

        function computeOverall(data) {
            const checks = data.checks || {};
            let anyYellow = false;
            let anyOptionalRed = false;

            for (const key of Object.keys(checks)) {
                const ch = checks[key];
                if (mandatoryFailed(key, ch)) {
                    return {
                        cls: "red",
                        text:
                            "A required check failed: PostgreSQL, Redis, Supabase (when configured), and required albandrieu.com infra HTTPS endpoints must be reachable.",
                    };
                }
                const c = classify(ch);
                if (c === "yellow") anyYellow = true;
                if (c === "red" && !MANDATORY.has(key)) anyOptionalRed = true;
            }

            const st = data.status;
            if (st && st !== "healthy") {
                anyYellow = true;
                const critical =
                    st === "health_fetch_failed" ||
                    st === "health_endpoint_non_200" ||
                    st === "health_invalid_json" ||
                    st === "health_unexpected_shape";
                if (critical) {
                    return {
                        cls: "red",
                        text: "Base /health check failed (" + st + ")." + (data.error ? " " + data.error : ""),
                    };
                }
            }

            if (anyOptionalRed) {
                return {
                    cls: "yellow",
                    text: "Core dependencies OK. One or more optional integrations are failing.",
                };
            }
            if (anyYellow) {
                return {
                    cls: "yellow",
                    text: "Core dependencies OK. Yellow = env not set (disabled on purpose) or minor /health note.",
                };
            }
            return {
                cls: "green",
                text: "All probed services are reachable.",
            };
        }

        function render(data) {
            const listEl = document.getElementById("health-checks");
            const summaryEl = document.getElementById("health-summary");
            const summaryText = document.getElementById("health-summary-text");
            const summaryLed = document.getElementById("health-summary-led");
            const errEl = document.getElementById("health-fetch-error");

            errEl.hidden = true;
            errEl.textContent = "";

            const overall = computeOverall(data);
            summaryEl.className = "health-summary health-summary--" + overall.cls;
            summaryLed.className = "health-led health-led--" + overall.cls;
            summaryText.textContent = overall.text;

            const checks = data.checks || {};
            const keys = sortKeys(Object.keys(checks));
            listEl.innerHTML = "";

            keys.forEach(function (key) {
                const check = checks[key];
                const tier = MANDATORY.has(key)
                    ? key.indexOf("albandrieu_") === 0
                        ? "Required infra (albandrieu.com)"
                        : "Required for core stack"
                    : "Optional integration";
                const cls = classify(check);
                const li = document.createElement("li");
                li.className = "health-row";
                li.innerHTML =
                    serviceIconSvg(key, cls) +
                    '<span class="health-row-led-wrap"><span class="health-led health-led--' +
                    cls +
                    '" title="' +
                    cls +
                    '"></span></span>' +
                    '<div class="health-row-main">' +
                    '<div class="health-row-primary health-row-primary--' +
                    cls +
                    '">' +
                    healthRowTitleHtml(check, key) +
                    '<div class="health-row-detail">' +
                    detailText(check) +
                    "</div></div>" +
                    '<div class="health-row-tags">' +
                    tier +
                    "</div>" +
                    "</div>";
                listEl.appendChild(li);
            });
        }

        function showFetchError(msg) {
            const summaryEl = document.getElementById("health-summary");
            const summaryText = document.getElementById("health-summary-text");
            const summaryLed = document.getElementById("health-summary-led");
            const errEl = document.getElementById("health-fetch-error");
            document.getElementById("health-checks").innerHTML = "";
            summaryEl.className = "health-summary health-summary--red";
            summaryLed.className = "health-led health-led--red";
            summaryText.textContent = "Could not load /healthz.";
            errEl.hidden = false;
            errEl.textContent = msg;
        }

        function classifySick(check) {
            if (check.skipped === true) return "yellow";
            if (check.reachable === true) return "red";
            if (check.reachable === false) return "green";
            return "gray";
        }

        function detailSickText(check) {
            if (check.skipped === true) {
                const intro = check.reason || "Not probed (LAN skip).";
                if (check.aliases_probed && check.aliases_probed.length) {
                    return (
                        intro +
                        " Targets: " +
                        check.aliases_probed.map(function (u) { return sickzShortHostForDetail(u); }).join(" · ")
                    );
                }
                return intro;
            }
            if (check.alias_results && check.aliases_probed) {
                const bits = [];
                check.aliases_probed.forEach(function (u) {
                    const r = check.alias_results[u];
                    const tail = sickzShortHostForDetail(u);
                    if (!r) return;
                    if (r.reachable === true) {
                        bits.push(
                            tail +
                                " → reachable" +
                                (r.http_status != null ? " (HTTP " + r.http_status + ")" : "")
                        );
                    } else if (r.error) {
                        bits.push(tail + " → unreachable (" + r.error + ")");
                    } else {
                        bits.push(tail + " → unreachable");
                    }
                });
                return bits.join(" · ");
            }
            if (check.reachable === true) {
                const parts = ["Reachable (should be blocked)."];
                if (check.http_status != null) parts.push("HTTP " + check.http_status);
                return parts.join(" ");
            }
            if (check.reachable === false) {
                if (check.error) return "Unreachable as expected. " + check.error;
                return "Unreachable as expected.";
            }
            return "Unknown state.";
        }

        function sickzNetworkPhrase(data) {
            return data.network_label ? '"' + data.network_label + '"' : "this deployment";
        }

        function computeSickOverall(data) {
            const net = sickzNetworkPhrase(data);
            if (data.status === "skipped_internal_network") {
                return {
                    cls: "yellow",
                    text:
                        (data.detail || "Sickz skipped on internal network.") +
                        " Network: " +
                        net +
                        ".",
                };
            }
            if (data.status === "no_targets" || Object.keys(data.checks || {}).length === 0) {
                return {
                    cls: "yellow",
                    text: (data.detail || "No sickz targets configured.") + " Network: " + net + ".",
                };
            }
            const checks = data.checks || {};
            for (const key of Object.keys(checks)) {
                const ch = checks[key];
                if (ch.skipped === true) continue;
                if (ch.reachable === true) {
                    return {
                        cls: "red",
                        text:
                            "From network " +
                            net +
                            ", at least one target is reachable; it should stay blocked from this context.",
                    };
                }
            }
            return {
                cls: "green",
                text:
                    "From network " +
                    net +
                    ", all listed targets are unreachable (expected).",
            };
        }

        function renderSickz(data) {
            const listEl = document.getElementById("sickz-checks");
            const summaryEl = document.getElementById("sickz-summary");
            const summaryText = document.getElementById("sickz-summary-text");
            const summaryLed = document.getElementById("sickz-summary-led");
            const errEl = document.getElementById("sickz-fetch-error");

            errEl.hidden = true;
            errEl.textContent = "";

            const overall = computeSickOverall(data);
            summaryEl.className = "health-summary health-summary--" + overall.cls;
            summaryLed.className = "health-led health-led--" + overall.cls;
            summaryText.textContent = overall.text;

            const hintEl = document.getElementById("sickz-lan-hint");
            const rt = data.runtime || {};
            if (hintEl) {
                if (data.status === "skipped_internal_network") {
                    hintEl.hidden = false;
                    if (rt.sickz_internal_network_implicit) {
                        hintEl.textContent =
                            "LAN skip was inferred from " +
                            (rt.internal_network_inferred_from || "SICKZ_NETWORK_LABEL / APP_DOMAIN rules") +
                            " (SICKZ_INTERNAL_NETWORK was not required).";
                    } else {
                        hintEl.textContent =
                            "LAN skip from SICKZ_INTERNAL_NETWORK=true.";
                    }
                } else if (rt.cloud_paas_detected && (rt.sickz_internal_network_config || rt.sickz_internal_network_implicit)) {
                    hintEl.hidden = false;
                    hintEl.textContent =
                        "Cloud/PaaS runtime: sickz probes still run even though this host would match home-LAN rules (env or implicit label/domain).";
                } else {
                    hintEl.hidden = true;
                    hintEl.textContent = "";
                }
            }

            const checks = data.checks || {};
            const keys = Object.keys(checks).sort();
            listEl.innerHTML = "";

            keys.forEach(function (key) {
                const check = checks[key];
                const cls = classifySick(check);
                const li = document.createElement("li");
                li.className = "health-row";
                const hrefRaw = (check.href || "").trim();
                const safeHref = hrefRaw.length ? sickzEscapeText(hrefRaw) : "#";
                const rowTitle = check.display_label || key;
                const lockTls = check.skipped === true ? null : check.tls_trusted;
                const lockHref = check.skipped === true ? "" : hrefRaw;
                li.innerHTML =
                    sickzRowIcon(check, cls) +
                    '<span class="health-row-led-wrap"><span class="health-led health-led--' +
                    cls +
                    '" title="' +
                    cls +
                    '"></span></span>' +
                    '<div class="health-row-main">' +
                    '<div class="health-row-primary health-row-primary--' +
                    cls +
                    '">' +
                    '<div class="health-row-name health-row-name--sickz">' +
                    sickzLockHtml(lockTls, lockHref) +
                    '<a class="sickz-target-link" target="_blank" rel="noopener noreferrer" href="' +
                    safeHref +
                    '">' +
                    sickzEscapeText(rowTitle) +
                    "</a></div>" +
                    '<div class="health-row-detail">' +
                    detailSickText(check) +
                    "</div></div>" +
                    '<div class="health-row-tags">' +
                    (check.skipped
                        ? "Listed for reference; not probed on this network"
                        : check.alias_results
                          ? "Equivalent URLs (any alias reachable fails the check)"
                          : "Must not be reachable") +
                    "</div>" +
                    "</div>";
                listEl.appendChild(li);
            });
        }

        function showSickzFetchError(msg) {
            const summaryEl = document.getElementById("sickz-summary");
            const summaryText = document.getElementById("sickz-summary-text");
            const summaryLed = document.getElementById("sickz-summary-led");
            const errEl = document.getElementById("sickz-fetch-error");
            document.getElementById("sickz-checks").innerHTML = "";
            summaryEl.className = "health-summary health-summary--red";
            summaryLed.className = "health-led health-led--red";
            summaryText.textContent = "Could not load /sickz.";
            errEl.hidden = false;
            errEl.textContent = msg;
        }

        function loadHealth() {
            fetch("/healthz", { headers: { Accept: "application/json" } })
                .then(function (r) {
                    if (!r.ok) throw new Error("HTTP " + r.status);
                    return r.json();
                })
                .then(render)
                .catch(function (e) {
                    showFetchError(String(e.message || e));
                });
        }

        function loadSickz() {
            fetch("/sickz", { headers: { Accept: "application/json" } })
                .then(function (r) {
                    if (!r.ok) throw new Error("HTTP " + r.status);
                    return r.json();
                })
                .then(renderSickz)
                .catch(function (e) {
                    showSickzFetchError(String(e.message || e));
                });
        }

        function loadHealthBoards() {
            loadHealth();
            loadSickz();
        }

        document.getElementById("health-refresh").addEventListener("click", loadHealthBoards);
        loadHealthBoards();
    })();
    </script>
    </body>
    </html>
    """
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


@app.get("/sentry-debug")
async def trigger_error() -> None:
    """Intentional error to verify Sentry (transaction + error event). See Sentry FastAPI docs."""
    _ = 1 / 0


# Error handling
@app.exception_handler(Exception)
def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled exception on {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "timestamp": datetime.now().isoformat()},
    )


parser = argparse.ArgumentParser(prog="nabla")
parser.add_argument("echo", help="String to print back to the console")


def main():
    args = parser.parse_args()
    print(args.echo)
