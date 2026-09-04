"""Unit tests for centralized SlowAPI wiring."""

from pathlib import Path

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


def test_no_route_module_constructs_an_independent_limiter() -> None:
    root = Path(__file__).resolve().parents[2]
    route_modules = (
        "nabla/routes.py",
        "nabla/api/demo/sensor.py",
        "nabla/api/v1.py",
        "nabla/api/ping.py",
    )

    for relative_path in route_modules:
        source = (root / relative_path).read_text(encoding="utf-8")
        assert "Limiter(" not in source
