"""Process-local Pyroscope profiler lifecycle helpers."""

from __future__ import annotations

import logging

import pyroscope

logger = logging.getLogger(__name__)


def start_pyroscope(
    *,
    enabled: bool,
    application_name: str,
    server_address: str,
) -> bool:
    """Start continuous profiling after the application worker has forked."""
    if not enabled:
        logger.info("Pyroscope profiling disabled")
        return False

    try:
        pyroscope.configure(
            application_name=application_name,
            server_address=server_address,
            sample_rate=100,
            enable_logging=True,
        )
    except Exception:
        logger.exception(
            "Pyroscope profiler initialization failed; application startup will continue"
        )
        return False

    logger.info(
        "Pyroscope profiling enabled application=%s server=%s",
        application_name,
        server_address,
    )
    return True


def stop_pyroscope(started: bool) -> None:
    """Stop the process-local profiler if this worker started it."""
    if not started:
        return
    try:
        pyroscope.shutdown()
    except Exception:
        logger.exception("Pyroscope profiler shutdown failed")
