"""Optional Datadog instrumentation helpers.

The application must remain bootable when ``ddtrace`` is not installed.
SDK components are imported lazily only when tracing, profiling, or an
authenticated user-context integration is explicitly enabled.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from nabla.utils.logger import logger


def _load_tracing() -> tuple[Any, Any, Any, Any] | None:
    """Load only the Datadog tracing components."""
    try:
        from ddtrace import config, patch, tracer
        from ddtrace.trace import TraceFilter
    except ImportError as exc:
        logger.warning(
            "datadog_sdk_unavailable",
            component="tracing",
            exception_type=type(exc).__name__,
        )
        return None
    return config, patch, tracer, TraceFilter


def _load_profiler() -> Any | None:
    """Load the profiler without importing tracing components."""
    try:
        from ddtrace.profiling import Profiler
    except ImportError as exc:
        logger.warning(
            "datadog_sdk_unavailable",
            component="profiling",
            exception_type=type(exc).__name__,
        )
        return None
    return Profiler


def _load_user_context() -> tuple[Any, Any] | None:
    """Load user-context helpers only for a future request integration."""
    try:
        from ddtrace import tracer
        from ddtrace.contrib.trace_utils import set_user
    except ImportError as exc:
        logger.warning(
            "datadog_sdk_unavailable",
            component="user_context",
            exception_type=type(exc).__name__,
        )
        return None
    return tracer, set_user


def configure_datadog(*, enabled: bool, app_name: str) -> bool:
    """Configure Datadog tracing when requested and available."""
    if not enabled:
        return False
    loaded = _load_tracing()
    if loaded is None:
        return False
    config, patch, tracer, trace_filter = loaded

    patch(fastapi=True, sqlalchemy=True)
    config.fastapi["service_name"] = app_name

    class FilterByName(trace_filter):
        """Filter out specific spans from traces."""

        def process_trace(self, trace):
            for span in trace:
                if span.name == "get_quote":
                    return None
            return trace

    tracer.configure(trace_processors=[FilterByName()])
    logger.info("Datadog tracing enabled")
    return True


def start_datadog_profiler(*, enabled: bool, app_name: str) -> Any | None:
    """Start the independently configured profiler and return its handle."""
    if not enabled:
        return None
    profiler_cls = _load_profiler()
    if profiler_cls is None:
        return None
    profiler = profiler_cls(env="prod", service=app_name)
    profiler.start()
    logger.info("Datadog profiler enabled")
    return profiler


def stop_datadog_profiler(profiler: Any | None) -> None:
    """Stop a profiler acquired for the application lifespan."""
    if profiler is None:
        return
    profiler.stop()
    logger.info("Datadog profiler stopped")


@contextmanager
def datadog_trace(
    *,
    enabled: bool,
    name: str,
    **kwargs: Any,
) -> Iterator[Any | None]:
    """Create a span lazily while remaining a no-op when tracing is disabled."""
    if not enabled:
        yield None
        return
    loaded = _load_tracing()
    if loaded is None:
        yield None
        return
    _, _, tracer, _ = loaded
    with tracer.trace(name, **kwargs) as span:
        yield span


def set_datadog_user(
    *,
    enabled: bool,
    user_id: str,
    name: str,
    email: str,
    scope: str,
    role: str,
    session_id: str,
) -> bool:
    """Set Datadog user context without making the SDK a startup dependency."""
    if not enabled:
        return False
    loaded = _load_user_context()
    if loaded is None:
        return False
    tracer, set_user = loaded
    set_user(
        tracer,
        user_id,
        name=name,
        email=email,
        scope=scope,
        role=role,
        session_id=session_id,
        propagate=True,
    )
    return True
