"""Unit tests for centralized SlowAPI wiring."""

from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded

from nabla.rate_limit import (
    configure_rate_limiting,
    limiter,
    rate_limit_exceeded_handler,
)


def test_configure_rate_limiting_uses_shared_limiter() -> None:
    app = FastAPI()

    configure_rate_limiting(app)

    assert app.state.limiter is limiter
    assert app.exception_handlers[RateLimitExceeded] is rate_limit_exceeded_handler
