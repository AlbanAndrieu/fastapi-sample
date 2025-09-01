import asyncio
import logging
import os
import re
import time
from datetime import datetime
from typing import Dict

import arel
import pyroscope
import redis
import sentry_sdk
from ddtrace import config, patch, tracer
from ddtrace.contrib.trace_utils import set_user
from ddtrace.profiling import Profiler
from ddtrace.trace import TraceFilter
from fastapi import APIRouter, FastAPI, Request
from fastapi.concurrency import asynccontextmanager
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi_mcp import FastApiMCP
from prometheus_client import make_asgi_app
from prometheus_fastapi_instrumentator import Instrumentator
from redis.client import Redis
from sentry_sdk.integrations.logging import LoggingIntegration
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount

from nabla.api import ping, v1, v2
from nabla.api.auth import keycloak
from nabla.api.demo import dd, demo, integration, sensor
from nabla.api.demo.models import recent_readings
from nabla.api.demo.sensor import metrics
from nabla.api.notes import notes
from nabla.api.test import info
from nabla.api.users import users
from nabla.auth.controller import AuthController
from nabla.config_settings import (
    APP_NAME,
    APP_PREFIX_VERSION,
    APP_VERSION,
    EXPOSE_MCP_PORT,
    OTLP_GRPC_ENDPOINT,
    REDIS_HOST,
    REDIS_PORT,
    SENTRY_DSN,
    get_settings,
)

# from nabla.db import database, engine, metadata
from nabla.db import database
from nabla.utils.log_config import LogMiddleware, setup_logging

# We need to load as soon as possible the setup_loggers
from nabla.utils.logger import logger
from nabla.utils.prometheus import (
    API_REQUEST_COUNTER,
    API_REQUEST_SUMMARY,
    REQUESTS,
    REQUESTS_IN_PROGRESS,
    REQUESTS_PROCESSING_TIME,
    RESPONSES,
    PrometheusMiddleware,
    setting_otlp,
    update_system_metrics,
)

prof = Profiler(
    env="prod",  # if not specified, falls back to environment variable DD_ENV
    service=APP_NAME,  # if not specified, falls back to environment variable DD_SERVICE
    # version="1.0.0",   # if not specified, falls back to environment variable DD_VERSION
)
prof.start()  # Should be as early as possible, eg before other imports, to ensure everything is profiled


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

# Global variable declaration
redis_conn: Redis | None = None


# Create tables
# metadata.create_all(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """background task starts at startup"""

    global redis_conn  # noqa: PLW0603
    redis_conn = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT)

    # redis_conn = Redis(
    #     host=REDIS_HOST,
    #     port=REDIS_PORT,
    #     decode_responses=True,
    #     max_connections=96,
    # )
    # print(redis_conn.get_nodes())

    await database.connect()

    """Start background system monitoring"""
    system_metrics_task = asyncio.create_task(update_system_metrics())

    logger.info("🚀 Sensor Dashboard application started successfully")
    logger.info(f"Debug mode: {bool(os.getenv('DEBUG'))}")
    logger.info(f"Initial sensor readings: {len(recent_readings)}")

    yield

    # Cancel the background task on shutdown
    system_metrics_task.cancel()

    await database.disconnect()

    if redis_conn:
        redis_conn.close()

    logger.info("📊 Sensor Dashboard application shutting down")
    logger.info(f"Final metrics - Connections: {metrics.connection_count}, Requests: {metrics.total_requests}")

@tracer.wrap()
async def _version(request: Request):
    return {"version": request.app.version}


class VersionedAPIRouter(APIRouter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.add_api_route(
            "/version",
            _version,
            methods=["GET"],
        )

def initialize_api_mcp() -> FastAPI:
    """
    Initialize the MCP API.

    :return: FastAPI
    :raise ValidationError: If there was an issue with the Settings
    """

    app_mcp = FastAPI(
        title=APP_NAME + " MCP  " + APP_PREFIX_VERSION,
        description="FastAPI MCP Sample for demo",
        version=f"{APP_PREFIX_VERSION}{APP_VERSION}",
        debug=os.getenv("DEBUG", "False").lower() == "true",
        base_url="http://localhost:" + str(EXPOSE_MCP_PORT),
    )

    mcp = FastApiMCP(
        app_mcp,
        name="FastAPI MCP Sample for demo",
        description="MCP server for my API",
        describe_all_responses=True,  # Include all possible response schemas
        describe_full_response_schema=True,  # Include full JSON schemas in descriptions
        # include_operations=["get_user", "create_user"],
        exclude_operations=["delete_user"],
        # include_tags=["users", "public"],
        exclude_tags=["admin", "internal"],
    )

    # Mount the MCP server to your app
    mcp.mount(app_mcp)

    return app_mcp


def initialize_api() -> FastAPI:
    """
    Initialize the API.

    :return: FastAPI
    :raise ValidationError: If there was an issue with the Settings
    """

    app = FastAPI(
        lifespan=lifespan,
        title=APP_NAME + " " + APP_PREFIX_VERSION,
        description="FastAPI Sample for demo",
        version=f"{APP_PREFIX_VERSION}{APP_VERSION}",
        debug=os.getenv("DEBUG", "False").lower() == "true",
    )

    app.add_middleware(LogMiddleware)

    origins = ["http://localhost", "http://localhost:8080", "http://localhost:8091", "http://localhost:8001", "*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["DELETE", "GET", "POST", "PUT"],
        allow_headers=["*"],
    )

    # Setting metrics middleware
    # PrometheusMiddleware seems not working BUT below metrics_middleware works
    app.add_middleware(
        PrometheusMiddleware,
        app_name=APP_NAME,
    )

    # app.add_middleware(
    #     metrics_middleware,
    #     app_name=APP_NAME,
    # )

    api_settings = get_settings()

    if api_settings.enable_metrics:
        instrumentator = Instrumentator(
            should_group_status_codes=False,
            should_ignore_untemplated=True,
            should_respect_env_var=True,
            should_instrument_requests_inprogress=True,
            excluded_handlers=["/metrics", "/health", "openapi.json", "docs"],
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

    v0_router = VersionedAPIRouter(
        prefix="/" + APP_PREFIX_VERSION,
    )

    app.include_router(v0_router)
    app.include_router(
        ping.router,
        tags=["ping"],
        responses={404: {"description": "Not found"}},
    )
    app.include_router(v1.router, tags=["api"])
    app.include_router(v2.router, tags=["api"])
    app.include_router(integration.router, tags=["integration"])
    app.include_router(dd.router, tags=["integration"])
    app.include_router(demo.router, tags=["integration"])
    app.include_router(notes.router, prefix="/notes", tags=["notes"])
    app.include_router(notes.router, prefix="/notes", tags=["notes"])
    app.include_router(info.router, tags=["test"])
    app.include_router(keycloak.router, tags=["auth"])
    app.include_router(sensor.router, tags=["sensor"])
    app.include_router(users.router, tags=["users"])

    return app


app = initialize_api()
app_mcp = initialize_api_mcp()

@app.middleware("http")
async def metrics_middleware(request, call_next):
    """
    🔧 Automatic metrics collection middleware
    This captures every request without modifying your business logic
    """
    start_time = time.time()

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

    response = await call_next(request)

    # Record comprehensive metrics
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

    REQUESTS_IN_PROGRESS.labels(
        method=request.method,
        path=request.url.path,
        app_name=APP_NAME,
    ).dec()
    return response


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
    email="alban.andrieu@free.com",
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
if os.getenv("DEBUG"):
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
def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/auth")
async def root():
    logger.info("Hello")
    """
    Root endpoint that provides a welcome message and documentation link.
    """
    return AuthController.read_root()


@app.get("/notes")
async def get_notes():
    API_REQUEST_COUNTER.labels(method="GET", endpoint="/notes", http_status=200).inc()
    API_REQUEST_SUMMARY.labels(method="GET", endpoint="/notes").observe(0.1)
    return await notes.read_all_notes()


@app.get("/notes/{id}")
async def get_note_by_id(idNote: int):
    API_REQUEST_COUNTER.labels(
        method="GET",
        endpoint="/notes/{id}",
        http_status=200,
    ).inc()
    API_REQUEST_SUMMARY.labels(method="GET", endpoint="/notes/{id}").observe(0.1)
    return await notes.read_note(idNote)


@app.post("/notes")
async def create_note():
    API_REQUEST_COUNTER.labels(method="POST", endpoint="/notes", http_status=200).inc()
    API_REQUEST_SUMMARY.labels(method="POST", endpoint="/notes").observe(0.1)
    return await notes.create_note()


@app.get("/health")
def get_status() -> Dict[str, str]:
    """Healthcheck endpoint."""
    with pyroscope.tag_wrapper({"function": "fast"}):
        return {"status": "alive_and_kicking", "timestamp": datetime.now().isoformat()}


@app.get("/sentry-debug")
async def trigger_error():
    pass

# Error handling
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url}: {exc}")
    return {"error": "Internal server error", "timestamp": datetime.now().isoformat()}
