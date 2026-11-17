"""Timed create_app phases (roadmap F08: three ~1 min pauses on TrueNAS boots)."""

import time
from collections.abc import Iterator
from contextlib import contextmanager

import psutil

from nabla.utils.logger import logger

# A phase over this bound logs a warning, so a slow boot names the phase that waits.
STARTUP_PHASE_WARN_SECONDS = 5.0


def log_startup_phase(name: str, seconds: float) -> None:
    """Log one phase duration; warn when it exceeds the bound."""
    slow = seconds >= STARTUP_PHASE_WARN_SECONDS
    (logger.warning if slow else logger.info)("startup_phase", phase=name, duration_ms=round(seconds * 1000), slow=slow)


@contextmanager
def startup_phase(name: str) -> Iterator[None]:
    """Time the wrapped create_app step, even when it raises."""
    started = time.perf_counter()
    try:
        yield
    finally:
        log_startup_phase(name, time.perf_counter() - started)


def log_import_phase() -> None:
    """Time from process start to create_app: the module imports run there."""
    try:
        created = psutil.Process().create_time()
    except (OSError, psutil.Error):
        return
    log_startup_phase("process_start_to_create_app", time.time() - created)
