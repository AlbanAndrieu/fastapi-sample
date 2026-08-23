"""HTTP middleware for metrics, logging, and request handling."""

import time

import sentry_sdk
from fastapi import Request
from starlette.routing import Match, Mount

from nabla.config_settings import APP_NAME
from nabla.utils.logger import logger
from nabla.utils.prometheus import (
    INFLIGHT_REQUESTS,
    REQUESTS,
    REQUESTS_IN_PROGRESS,
    REQUESTS_PROCESSING_TIME,
    RESPONSES,
)

_NOISY_SUCCESS_PATHS = frozenset(
    {
        "/api/homelab-services",
        "/api/homelab/health",
        "/docs",
        "/health",
        "/healthz",
        "/metrics",
        "/openapi.json",
        "/sickz",
    }
)
_NOISY_SUCCESS_PREFIXES = ("/mcp", "/logs/", "/stream/", "/v1/mcp/")


def metric_route_label(request: Request) -> str:
    """Return a stable route template instead of an unbounded request path."""
    current_route = request.scope.get("route")
    if current_route is not None:
        route_template = getattr(current_route, "path_format", None)
        if route_template:
            return route_template

    for route in request.app.routes:
        if isinstance(route, Mount):
            continue
        match, _ = route.matches(request.scope)
        if match is Match.FULL:
            return getattr(route, "path_format", route.path)

    return "__unmatched__"


async def metrics_middleware(request: Request, call_next):
    """Automatic metrics collection middleware."""
    start_time = time.time()
    route_label = metric_route_label(request)
    INFLIGHT_REQUESTS.inc()
    REQUESTS_IN_PROGRESS.labels(
        method=request.method, path=route_label, app_name=APP_NAME
    ).inc()
    REQUESTS.labels(
        method=request.method, path=route_label, app_name=APP_NAME
    ).inc()

    try:
        response = await call_next(request)
        elapsed_ms = int((time.time() - start_time) * 1000)
        if request.url.path == "/docs":
            sentry_sdk.metrics.distribution(
                "page_load", elapsed_ms, unit="millisecond", attributes={"page": "/docs"}
            )
        elif request.url.path.startswith("/api"):
            sentry_sdk.metrics.gauge(
                "page_load", elapsed_ms, unit="millisecond", attributes={"page": "/api"}
            )
        RESPONSES.labels(
            method=request.method,
            path=route_label,
            status_code=response.status_code,
            app_name=APP_NAME,
        ).inc()
        REQUESTS_PROCESSING_TIME.labels(
            method=request.method, path=route_label, app_name=APP_NAME
        ).observe(time.time() - start_time)
        return response
    finally:
        INFLIGHT_REQUESTS.dec()
        REQUESTS_IN_PROGRESS.labels(
            method=request.method, path=route_label, app_name=APP_NAME
        ).dec()


async def logging_middleware(request: Request, call_next):
    """Request/response logging middleware."""
    start_time = time.time()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed", method=request.method, path=request.url.path
        )
        raise

    duration = time.time() - start_time
    log_fields = {
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_seconds": duration,
    }
    is_noisy = (
        response.status_code < 400
        and (
            request.url.path in _NOISY_SUCCESS_PATHS
            or request.url.path.startswith(_NOISY_SUCCESS_PREFIXES)
        )
    )

    if response.status_code >= 500:
        logger.error("request_completed", **log_fields)
    elif response.status_code >= 400 or duration >= 2.0:
        logger.warning("request_completed", **log_fields)
    elif not is_noisy:
        logger.info("request_completed", **log_fields)

    return response
