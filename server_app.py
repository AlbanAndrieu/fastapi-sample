import logging
import argparse

import pyroscope
import uvicorn.config
from pydantic import ValidationError

from nabla.config_settings import (
    APP_NAME,
    EXPOSE_HOST,
    EXPOSE_PORT,
    PYROSCOPE_ENDPOINT,
    get_settings,
)
from nabla.main import app
from nabla.utils.log_config import setup_logging

logger = logging.getLogger(__name__)
logger.level = logging.INFO


def uvicorn_run() -> None:
    """Run as a Uvicorn server."""

    exit_code = 0
    try:
        pyroscope.configure(
            application_name=APP_NAME,
            server_address=PYROSCOPE_ENDPOINT,  # See https://grafana.com/docs/pyroscope/next/configure-client/language-sdks/python/
            # server_port=EXPOSE_PORT,
            # service_name="fastapi-sample",
            # trace_id_key="otelTraceID",
            # span_id_key="otelSpanID",
            sample_rate=100,  # default is 100
        )

        setup_logging()

        try:
            logger.info("Initializing API")

            api_settings = get_settings()

            config = uvicorn.Config(
                app,
                host=EXPOSE_HOST,
                port=EXPOSE_PORT,
                log_config=None,
                log_level=api_settings.api_log_level,
                reload=True,
            )
            server = uvicorn.Server(config)
            server.run()
        except ValidationError:
            logger.exception("There was a problem with the environment settings")
            exit(1)
        except Exception:
            logger.exception("Unknown Error")
            exit(2)

    except AttributeError as e:
        logger.error(f"API port is missing from the settings: {e}")
        exit_code = 1
    finally:
        exit(exit_code)


def main():
    logger = logging.getLogger(__name__)
    uvicorn_run()


parser = argparse.ArgumentParser(prog="server_app")
parser.add_argument("echo", help="String to print back to the console")

if __name__ == "__main__":
    args = parser.parse_args()
    print(args.echo)
    main()
