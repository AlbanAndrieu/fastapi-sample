"""HTTP middleware for metrics, logging, and request handling."""
import time
from fastapi import Request
from nabla.utils.logger import logger
from nabla.utils.prometheus import (
    INFLIGHT_REQUESTS,
    REQUESTS,
    REQUESTS_IN_PROGRESS,
    REQUESTS_PROCESSING_TIME,
    RESPONSES,
)
from nabla.config_settings import APP_NAME
from nabla.config import NOISY_SUCCESS_PATHS, NOISY_SUCCESS_PREFIXES


async def metrics_middleware(request: Request, call_next):
    """Automatic metrics collection middleware."""
    start_time = time.time()
    INFLIGHT_REQUESTS.inc()
    REQUESTS_IN_PROGRESS.labels(
        method=request.method, path=request.url.path, app_name=APP_NAME
    ).inc()
    REQUESTS.labels(
        method=request.method, path=request.url.path, app_name=APP_NAME
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
            method=request.method, path=request.url.path, app_name=APP_NAME
        ).observe(time.time() - start_time)
        return response
    finally:
        INFLIGHT_REQUESTS.dec()
        REQUESTS_IN_PROGRESS.labels(
            method=request.method, path=request.url.path, app_name=APP_NAME
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
