import asyncio
import time
from abc import ABC
from typing import Callable, Tuple

import psutil
from fastapi import Request
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import REGISTRY, Counter, Gauge, Histogram
from prometheus_client.openmetrics.exposition import (
    CONTENT_TYPE_LATEST,
    generate_latest,
)
from prometheus_fastapi_instrumentator.metrics import Info
from pydantic_settings import BaseSettings
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.routing import Match
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR
from starlette.types import ASGIApp

# See https://github.com/KenMwaura1/Fast-Api-Grafana-Starter/blob/main/src/app/main.py
# Or https://medium.com/@diwasb54/building-a-production-ready-monitoring-stack-for-fastapi-applications-a-complete-guide-with-bce2af74d258
#
# See https://github.com/blueswen/fastapi-observability/blob/main/fastapi_app/utils.py

INFO = Gauge("fastapi_app_info", "FastAPI application information.", ["app_name"])
REQUESTS = Counter(
    "fastapi_requests_total",  # http_requests_total"
    "Total count of requests by method and path.",
    ["method", "path", "app_name"],
)
RESPONSES = Counter(
    "fastapi_responses_total",  # to be kept
    "Total count of responses by method, path and status codes.",
    ["method", "path", "status_code", "app_name"],
)
REQUESTS_PROCESSING_TIME = Histogram(
    "fastapi_requests_duration_seconds",  # renamed http_request_duration_seconds_bucket
    "Histogram of requests processing time by path (in seconds)",
    ["method", "path", "app_name"],
)
EXCEPTIONS = Counter(
    "fastapi_exceptions_total",  # to be kept
    "Total count of exceptions raised by path and exception type",
    ["method", "path", "exception_type", "app_name"],
)
REQUESTS_IN_PROGRESS = Gauge(
    "fastapi_requests_in_progress",  # renamed http_requests_in_progress
    "Gauge of requests by method and path currently being processed",
    ["method", "path", "app_name"],
)

# Define a counter metric

CPU_USAGE = Gauge("system_cpu_usage_percent", "System CPU usage percentage")
MEMORY_USAGE = Gauge("system_memory_usage_percent", "System memory usage percentage")


API_REQUEST_COUNTER = Counter(
    "api_request_counter",
    "Request processing time",
    ["method", "endpoint", "http_status"],
)
API_REQUEST_SUMMARY = Histogram(
    "api_request_summary",
    "Request processing time",
    ["method", "endpoint"],
)
# # Define a histogram metric
# REQUESTS_TIME = Histogram(
#     "requests_time", "Request processing time", ["method", "endpoint"]
# )


ERROR_COUNT = Counter(
    "errors_total",
    "The total number of errors.",
    ["error"],
)  # Triggered by exception, TODO replace by EXCEPTIONS
# See https://signoz.io/blog/opentelemetry-fastapi/
# https://github.com/SigNoz/sample-fastAPI-app/blob/main/app/main.py

DD_API_LATENCY = Histogram(
    name="dd_api_latency",
    documentation="The time taken for a call on the defact dojo api",
    labelnames=["api"],
    buckets=(1, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 25, 30, 40, 50),
)

DD_CRITICAL_FINDINGS_COUNT = Gauge(
    "dd_critical_findings_count",
    "The number of critical findings",
    labelnames=["product"],
)
DD_HIGH_FINDINGS_COUNT = Gauge(
    "dd_high_findings_count",
    "The number of high findings",
    labelnames=["product"],
)
DD_MEDIUM_FINDINGS_COUNT = Gauge(
    "dd_medium_findings_count",
    "The number of medium findings",
    labelnames=["product"],
)
DD_LOW_FINDINGS_COUNT = Gauge(
    "dd_low_findings_count",
    "The number of low findings",
    labelnames=["product"],
)
DD_INFO_FINDINGS_COUNT = Gauge(
    "dd_info_findings_count",
    "The number of info findings",
    labelnames=["product"],
)

# Add to your FastAPI app
USER_REGISTRATIONS = Counter("user_registrations_total", "Total user registrations")
ORDER_VALUE = Histogram("order_value_dollars", "Order value distribution")
ACTIVE_USERS = Gauge("active_users_current", "Currently active users")


async def update_system_metrics():
    """
    📊 Continuous system metrics collection
    Updates every 5 seconds with current system state
    """
    while True:
        CPU_USAGE.set(psutil.cpu_percent())
        MEMORY_USAGE.set(psutil.virtual_memory().percent)
        await asyncio.sleep(5)


# See https://github.com/blueswen/fastapi-observability/blob/main/fastapi_app/utils.py


# PrometheusMiddleware seems not working BUT metrics_middleware works
class PrometheusMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, app_name: str = "fastapi-app") -> None:
        super().__init__(app)
        self.app_name = app_name
        self.prefix = "nabla"
        self.skip_paths = [
            "/health",
            "/ping",
            "/v1/ping",
            "/v2/ping",
            "/docs",
            "/version",
            "io_task",
            "cpu_task",
            "server-status",
            "openapi.json",
        ]
        # self.exemplars=lambda: {"trace_id": get_trace_id}  # function that returns a trace id
        INFO.labels(app_name=self.app_name).inc()

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        method = request.method
        path, is_handled_path = self.get_path(request)

        if not is_handled_path:
            return await call_next(request)

        REQUESTS_IN_PROGRESS.labels(
            method=method,
            path=path,
            app_name=self.app_name,
        ).inc()
        REQUESTS.labels(method=method, path=path, app_name=self.app_name).inc()
        before_time = time.perf_counter()
        try:
            response = await call_next(request)
        except BaseException as e:
            status_code = HTTP_500_INTERNAL_SERVER_ERROR
            EXCEPTIONS.labels(
                method=method,
                path=path,
                exception_type=type(e).__name__,
                app_name=self.app_name,
            ).inc()
            raise e from None
        else:
            status_code = response.status_code
            after_time = time.perf_counter()
            # retrieve trace id for exemplar
            span = trace.get_current_span()
            trace_id = trace.format_trace_id(span.get_span_context().trace_id)

            REQUESTS_PROCESSING_TIME.labels(
                method=method,
                path=path,
                app_name=self.app_name,
            ).observe(after_time - before_time, exemplar={"TraceID": trace_id})
        finally:
            RESPONSES.labels(
                method=method,
                path=path,
                status_code=status_code,  # type: ignore
                app_name=self.app_name,
            ).inc()
            REQUESTS_IN_PROGRESS.labels(
                method=method,
                path=path,
                app_name=self.app_name,
            ).dec()

        return response

    @staticmethod
    def get_path(request: Request) -> Tuple[str, bool]:
        for route in request.app.routes:
            match = route.matches(request.scope)
            if match == Match.FULL:
                return route.path, True

        return request.url.path, False


def http_requested_languages_total() -> Callable[[Info], None]:
    METRIC = Counter(
        "http_requested_languages_total",
        "Number of times a certain language has been requested.",
        labelnames=("langs",),
    )

    def instrumentation(info: Info) -> None:
        langs = set()
        lang_str = info.request.headers["Accept-Language"]
        for element in lang_str.split(","):
            element = element.split(";")[0].strip().lower()  # noqa: PLW2901
            langs.add(element)
        for language in langs:
            METRIC.labels(language).inc()

    return instrumentation


def metrics(request: Request) -> Response:
    return Response(
        generate_latest(REGISTRY),
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )


def setting_otlp(
    app: ASGIApp,
    app_name: str,
    endpoint: str,
    log_correlation: bool = True,
) -> None:
    # Setting OpenTelemetry
    # set the service name to show in traces
    resource = Resource.create(
        attributes={"service.name": app_name, "compose_service": app_name},
    )

    # set the tracer provider
    tracer = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer)

    # exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    # JaegerExporter()

    tracer.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))

    if log_correlation:
        LoggingInstrumentor().instrument(set_logging_format=True)

    FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer)  # type: ignore


class PrometheusSettings(BaseSettings, ABC):
    enable_metrics: bool
