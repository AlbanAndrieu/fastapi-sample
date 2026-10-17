# pylint: disable=wrong-import-position

"""Production FastAPI application entry point.

The application is assembled by :func:`nabla.app_factory.create_app`; this
module keeps the historical ``nabla.main:app`` / ``nabla.main.mcp`` exports.
"""

import argparse

from pybreaker import CircuitBreaker

from nabla.utils.log_config import setup_logging
from nabla.utils.logger import logger

setup_logging()
logger.info("Creating API")

from nabla.app_factory import AppFeatures, create_app  # noqa: E402

__all__ = ["AppFeatures", "app", "circuit_breaker_web", "create_app", "main", "mcp", "mcp_app"]

circuit_breaker_web = CircuitBreaker(fail_max=2, reset_timeout=10)

app = create_app()
mcp = app.state.mcp
mcp_app = app.state.mcp_app

parser = argparse.ArgumentParser(prog="nabla")
parser.add_argument("echo", help="String to print back to the console")


def main():
    """CLI entry point."""
    args = parser.parse_args()
    print(args.echo)


if __name__ == "__main__":
    main()
