import logging
import os
import re
from typing import Dict

import logfire
import pyroscope
import sentry_sdk
from ddtrace import config, patch, tracer
from fastapi import APIRouter, FastAPI, Request
from fastapi.openapi.utils import get_openapi
from prometheus_client import make_asgi_app
from sentry_sdk import set_user
from sentry_sdk.integrations.logging import LoggingIntegration

# from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount

from nabla.api import ping, v1, v2
from nabla.api.notes import notes
from nabla.db import database, engine, metadata
from nabla.metrics.prometheus import API_REQUEST_COUNTER, API_REQUEST_SUMMARY

# We need to load as soon as possible the setup_loggers
# from nabla.logger import logger
from nabla.utils.log_config import setup_logging
from nabla.utils.log_middleware import LogMiddleware
from nabla.utils.prometheus import PrometheusMiddleware, setting_otlp

# from citation.infrastructure.crud_exceptions import CrudError, NotFoundInJM


APP_NAME = os.environ.get("APP_NAME", "fastapi-sample")
APP_PREFIX_VERSION = os.environ.get("APP_PREFIX_VERSION", "v0")
APP_VERSION = os.environ.get("APP_VERSION", "1.0.6")

DD_AGENT_HOST = os.environ.get("DD_AGENT_HOST", "127.0.0.1")
DD_TRACE_AGENT_PORT = os.environ.get("DD_TRACE_AGENT_PORT", "8126")

# http://grpc.jaeger-collector-grpc.service.gra.dev.consul
# http://jaeger-collector-grpc.service.gra.dev.consul:14250
# http://otel-collector.service.gra.dev.consul:4317
# http://otel-collector.service.gra.dev.consul:9411/api/v2/spans


OTLP_GRPC_ENDPOINT = os.environ.get(
    # "OTLP_GRPC_ENDPOINT", "http://grpc.jaeger-collector-grpc.service.gra.dev.consul"
    "OTLP_GRPC_ENDPOINT",
    "http://otel-collector.service.gra.dev.consul:4317",
)

OTEL_EXPORTER_JAEGER_AGENT_HOST = os.environ.get(
    "OTEL_EXPORTER_JAEGER_AGENT_HOST", "jaeger-collector-grpc.service.gra.dev.consul"
)

OTEL_EXPORTER_JAEGER_AGENT_PORT = os.environ.get(
    "OTEL_EXPORTER_JAEGER_AGENT_PORT", "80"
)

OTEL_EXPORTER_JAEGER_ENDPOINT = os.environ.get(
    "OTEL_EXPORTER_JAEGER_ENDPOINT",
    "http://jaeger-collector-grpc.service.gra.dev.consul:14250",
)

SENTRY_DSN = os.environ.get(
    "SENTRY_DSN",
    "https://11c5d815632831d3274c830441885207@o4505783360356352.ingest.sentry.io/4505783364681728",
)

setup_logging()

metadata.create_all(engine)


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
        "url": "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png"
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


logfire.info("Hello, {name}!", name="World")

logger = logging.getLogger(__name__)
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

# Unix domain socket configuration
tracer.configure(
    uds_path="/var/run/datadog/apm.socket",
)

# Network socket
# tracer.configure(
#    dogstatsd_url="udp://127.0.0.1:8125",
# )

# Unix domain socket configuration
tracer.configure(
    dogstatsd_url="unix:///var/run/datadog/dsd.socket",
)

app = FastAPI(
    title=APP_NAME + " " + APP_PREFIX_VERSION,
    description="FastAPI Sample for demo",
    version="v0." + APP_VERSION,
    debug=False,
)

app.add_middleware(LogMiddleware)


origins = ["http://localhost", "http://localhost:8080", "http://localhost:5173", "*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["DELETE", "GET", "POST", "PUT"],
    allow_headers=["*"],
)

# Setting metrics middleware
app.add_middleware(
    PrometheusMiddleware,
    app_name=APP_NAME,
)

# Add prometheus asgi middleware to route /metrics requests
# metrics_app = make_asgi_app()
# app.mount("/metrics", metrics_app)

# Add prometheus asgi middleware to route /metrics requests
# https://github.com/prometheus/client_python/issues/1016
route = Mount("/metrics", make_asgi_app())
route.path_regex = re.compile("^/metrics(?P<path>.*)$")
app.routes.append(route)

# Setting OpenTelemetry exporter
setting_otlp(app, APP_NAME, OTLP_GRPC_ENDPOINT)

set_user({"email": "alban.andrieu@free.com"})

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


@app.get("/")
async def read_root():
    logger.info("Hello")
    return {"Hello": "World"}


@app.get("/notes")
async def get_notes():
    API_REQUEST_COUNTER.labels(method="GET", endpoint="/notes", http_status=200).inc()
    API_REQUEST_SUMMARY.labels(method="GET", endpoint="/notes").observe(0.1)
    return await notes.read_all_notes()


@app.get("/notes/{id}")
async def get_note_by_id(idNote: int):
    API_REQUEST_COUNTER.labels(
        method="GET", endpoint="/notes/{id}", http_status=200
    ).inc()
    API_REQUEST_SUMMARY.labels(method="GET", endpoint="/notes/{id}").observe(0.1)
    return await notes.read_note(idNote)


@app.post("/notes")
async def create_note():
    API_REQUEST_COUNTER.labels(method="POST", endpoint="/notes", http_status=200).inc()
    API_REQUEST_SUMMARY.labels(method="POST", endpoint="/notes").observe(0.1)
    return await notes.create_note()


# @app.exception_handler(NotFoundInJM)
# async def not_found_jm_handler(request: Request, exc: NotFoundInJM):
#    return JSONResponse(
#        status_code=404,
#        content={"message": str(exc)},
#    )
#
#
# @app.exception_handler(CrudError)
# async def crud_error_handler(request: Request, exc: CrudError):
#    logger.error("Error while querying the DB")
#    logger.exception(exc)
#    return JSONResponse(
#        status_code=500,
#        content={"message": f"Error while querying the DB: {exc}"},
#    )
#
#
# @app.exception_handler(Exception)
# async def exception_handler(request: Request, exc: Exception):
#    logger.error("Unexpected error")
#    logger.exception(exc)
#    return JSONResponse(
#        status_code=500,
#        content={"message": f"Unexpected error: {exc}"},
#    )


@app.on_event("startup")
async def startup():
    await database.connect()
    # # Instrumentator().instrument(app).expose(app)
    # FastAPIInstrumentor.instrument_app(app)
    logger.info("API is ready")


@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()


@app.get("/health")
def get_status() -> Dict[str, str]:
    """Healthcheck endpoint."""
    with pyroscope.tag_wrapper({"function": "fast"}):
        return {"status": "pass"}


@app.get("/sentry-debug")
async def trigger_error():
    pass


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


v0_router = VersionedAPIRouter(
    prefix="/" + APP_PREFIX_VERSION,
)

app.include_router(v0_router)
app.include_router(
    ping.router, tags=["ping"], responses={404: {"description": "Not found"}}
)
app.include_router(v1.router)
app.include_router(v2.router)
app.include_router(notes.router, prefix="/notes", tags=["notes"])
app.include_router(notes.router, prefix="/notes", tags=["notes"])
