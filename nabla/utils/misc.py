import time
from contextlib import contextmanager

from metrics.prometheus import DD_API_LATENCY

from nabla.logger import logger


@contextmanager
def timed_operation(name: str):
    """Context manager to measure and print the duration of a block of code."""
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        logger.info(f"{name} time taken: {duration:.2f} seconds")
        DD_API_LATENCY.labels({"step": name}).observe(duration)
