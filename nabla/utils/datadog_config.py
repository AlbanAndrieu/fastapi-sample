"""Optional Datadog instrumentation helpers.

The application must remain bootable when ``ddtrace`` is not installed.
The SDK is imported lazily only when Datadog tracing is explicitly enabled.
"""

from __future__ import annotations

from typing import Any

from nabla.utils.logger import logger


def _load_ddtrace() -> tuple[Any, Any, Any, Any, Any] | None:
    """Load Datadog lazily, returning ``None`` when the optional SDK is absent."""
    try:
        from ddtrace import config, patch, tracer
        from ddtrace.contrib.trace_utils import set_user
        from ddtrace.profiling import Profiler
    except ImportError as exc:
        logger.warning("Datadog tracing requested but ddtrace is unavailable: %s", exc)
        return None
    return config, patch, tracer, set_user, Profiler


def configure_datadog(*, enabled: bool, app_name: str) -> bool:
    """Configure Datadog tracing when requested and available."""
    if not enabled:
        return False
    loaded = _load_ddtrace()
    if loaded is None:
        return False
    config, patch, tracer, _, _ = loaded
    try:
        from ddtrace.trace import TraceFilter
    except ImportError as exc:
        logger.warning("Datadog TraceFilter unavailable; tracing disabled: %s", exc)
        return False

    patch(fastapi=True)
    config.fastapi["service_name"] = app_name

    class FilterByName(TraceFilter):
        """Filter out specific spans from traces."""

        def process_trace(self, trace):
            for span in trace:
                if span.name == "get_quote":
                    return None
            return trace

    tracer.configure(trace_processors=[FilterByName()])
    logger.info("Datadog tracing enabled")
    return True


def start_datadog_profiler(*, app_name: str) -> bool:
    """Start the Datadog profiler if the SDK is available."""
    loaded = _load_ddtrace()
    if loaded is None:
        return False
    _, _, _, _, profiler_cls = loaded
    profiler = profiler_cls(env="prod", service=app_name)
    profiler.start()
    logger.info("Datadog profiler enabled")
    return True


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
    loaded = _load_ddtrace()
    if loaded is None:
        return False
    _, _, tracer, set_user, _ = loaded
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
