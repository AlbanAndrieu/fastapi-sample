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

from nabla.api import brave_route, google_search_route, ping, tavily_route, v1, v2
from nabla.api.auth import keycloak
from nabla.api.db.database import SessionLocal, database, engine, init_db
from nabla.api.demo import dd, demo, integration, sensor
from nabla.api.demo.models import init_db as init_db_sensor_reading
from nabla.api.demo.models import recent_readings
from nabla.api.demo.sensor import metrics
from nabla.api.demo.socket.redis import redis, start_event_listener
from nabla.api.demo.socket.websocket import websocket_endpoint
from nabla.api.health_checks import build_healthz_payload
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
    app.include_router(tavily_route.router, tags=["tavily"])
    app.include_router(brave_route.router, tags=["brave"])
    app.include_router(google_search_route.router, tags=["google"])
    app.include_router(integration.router, tags=["integration"])
    app.include_router(dd.router, tags=["integration"])
    app.include_router(demo.router, tags=["integration"])
    app.include_router(notes.router, tags=["notes"])
    app.include_router(info.router, tags=["test"])
    app.include_router(keycloak.router, tags=["keycloak"])
    app.include_router(users.router, tags=["users"])
    app.include_router(sensor.router, tags=["sensor"])

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
    TITLE_SUFFIX = os.getenv("TITLE")
    app_version = html.escape(str(request.app.version))
    return (
        """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Vercel + FastAPI """
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
                <a href="/" class="logo">Vercel + FastAPI """
        + str(TITLE_SUFFIX)
        + """</a>
                <div class="nav-links">
                    <a href="/docs">API Docs</a>
                    <a href="/api/data">API</a>
                </div>
            </nav>
        </header>
        <main>
            <div class="hero">
                <h1>Vercel + FastAPI """
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
    </body>
    </html>
    """
    )


@app.get("/healthz")
async def get_healthz(request: Request) -> Dict[str, Any]:
    """Deep healthcheck: merges ``GET /health`` with Redis, Postgres, Supabase, and OVH ``/me`` probes."""
    with pyroscope.tag_wrapper({"function": "fast"}):
        return await build_healthz_payload(request, redis_client=redis, engine=engine)


@app.get("/sentry-debug")
def trigger_error():
    pass


# Error handling
@app.exception_handler(Exception)
def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url}: {exc}")
    return {"error": "Internal server error", "timestamp": datetime.now().isoformat()}


parser = argparse.ArgumentParser(prog="nabla")
parser.add_argument("echo", help="String to print back to the console")


def main():
    args = parser.parse_args()
    print(args.echo)
