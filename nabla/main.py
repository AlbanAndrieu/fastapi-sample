import logging
import os
import time
from typing import Dict

import pyroscope
import sentry_sdk
from fastapi import FastAPI

# from nabla import logger
from nabla.api import ping, v1
from nabla.log_middleware import LogMiddleware
from nabla.logger import logger
from nabla.utils import PrometheusMiddleware, metrics, setting_otlp
from sentry_sdk.integrations.logging import LoggingIntegration

# from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.cors import CORSMiddleware

# from citation.infrastructure.crud_exceptions import CrudError, NotFoundInJM


APP_NAME = os.environ.get("APP_NAME", "nabla-hooks")
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

# http://grpc.jaeger-collector-grpc.service.gra.dev.consul
# http://jaeger-collector-grpc.service.gra.dev.consul:14250
# http://otel-collector.service.gra.dev.consul:4317
# http://otel-collector.service.gra.dev.consul:9411/api/v2/spans

sentry_sdk.init(
    dsn=SENTRY_DSN,
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    # We recommend adjusting this value in production,
    traces_sample_rate=1.0,
    integrations=[
        LoggingIntegration(
            level=logging.INFO,  # Capture info and above as breadcrumbs
            event_level=logging.ERROR,  # Send errors as events
        ),
    ],
)

# logger.info("Creating API")
logging.info("Creating API")
app = FastAPI(
    title="FastAPI Sample V1",
    description="FastAPI Sample V1",
    version="0.0.1",
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

app.add_route("/metrics", metrics)

# Setting OpenTelemetry exporter
setting_otlp(app, APP_NAME, OTLP_GRPC_ENDPOINT)


@app.get("/")
async def read_root():
    logger.info("Hello")
    return {"Hello": "World"}


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
@app.get("/io_task")
async def io_task():
    time.sleep(1)
    logging.error("io task")
    return "IO bound task finish!"


def work(n):
    for i in range(n):
        i * i * i


@app.get("/cpu_task")
async def cpu_task():
    with pyroscope.tag_wrapper({"function": "fast"}):
        work(1000)
    logging.error("cpu task")
    return "CPU bound task finish!"


@app.on_event("startup")
async def startup():
    # await database.connect()
    # # Instrumentator().instrument(app).expose(app)
    # FastAPIInstrumentor.instrument_app(app)
    logging.info("API is ready")


# @app.on_event("shutdown")
# async def shutdown():
#     await database.disconnect()


@app.get("/health")
def get_status() -> Dict[str, str]:
    """Healthcheck endpoint."""
    with pyroscope.tag_wrapper({"function": "fast"}):
        return {"status": "pass"}


@app.get("/sentry-debug")
async def trigger_error():
    pass


app.include_router(ping.router)
app.include_router(v1.router)
# app.include_router(notes.router, prefix="/notes", tags=["notes"])
