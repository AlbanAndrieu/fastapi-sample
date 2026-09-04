"""Shared SlowAPI rate-limiting configuration.

Keep one limiter instance for all explicitly decorated routes. Global/default
limits remain intentionally disabled until their behavior is validated against
the resolved FastAPI version and the deployment's trusted client-IP model.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    key_prefix="fastapi-sample",
)


async def rate_limit_exceeded_handler(
    _request: Request,
    _exc: RateLimitExceeded,
) -> JSONResponse:
    """Return the stable public response used for explicit route limits."""
    return JSONResponse(
        status_code=429,
        content={"error": "Too Many Requests"},
    )


def configure_rate_limiting(app: FastAPI) -> None:
    """Attach the shared limiter and its exception handler to one application."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
