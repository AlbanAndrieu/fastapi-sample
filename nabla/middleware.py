"""HTTP middleware for metrics, logging, and request handling."""

import time

from fastapi import Request
from starlette.routing import Match, Mount

from nabla.config import NOISY_SUCCESS_PATHS, NOISY_SUCCESS_PREFIXES
from nabla.config_settings import APP_NAME, get_settings
from nabla.utils.logger import logger
from nabla.utils.prometheus import (
    INFLIGHT_REQUESTS,
    REQUESTS,
    REQUESTS_IN_PROGRESS,
    REQUESTS_PROCESSING_TIME,
    RESPONSES,
)


def _route_template(route: object) -> str | None:
    """Return a route path without assuming a concrete Starlette route type."""
    for attribute in ("path_format", "path"):
        value = getattr(route, attribute, None)
        if isinstance(value, str) and value:
            return value
    return None


def metric_route_label(request: Request) -> str:
    """Return a bounded-cardinality route template for Prometheus labels."""
    current_route = request.scope.get("route")
    if current_route is not None:
        route_template = _route_template(current_route)
        if route_template:
            return route_template

    for route in request.app.routes:
        if isinstance(route, Mount):
            continue
        match, _ = route.matches(request.scope)
        if match is Match.FULL:
            return _route_template(route) or "__unmatched__"

    return "__unmatched__"


async def metrics_middleware(request: Request, call_next):
    """Automatic metrics collection middleware."""
    if not get_settings().metrics_enabled:
        return await call_next(request)

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
            request.url.path in NOISY_SUCCESS_PATHS
            or request.url.path.startswith(NOISY_SUCCESS_PREFIXES)
        )
    )

    if response.status_code >= 500:
        logger.error("request_completed", **log_fields)
    elif response.status_code >= 400 or duration >= 2.0:
        logger.warning("request_completed", **log_fields)
    elif not is_noisy:
        logger.info("request_completed", **log_fields)

    return response
