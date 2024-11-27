import logging
import os

import pyroscope
import uvicorn.config

from nabla.fastapi_server import app
from nabla.utils.log_config import setup_logging

EXPOSE_HOST = os.environ.get("EXPOSE_HOST", "0.0.0.0")  # noqa: S104 noqa:B104
EXPOSE_PORT = int(os.environ.get("EXPOSE_PORT", 8080))
PYROSCOPE_ENDPOINT = os.environ.get("PYROSCOPE_ENDPOINT", "http://localhost:4040")


def uvicorn_run() -> None:
    """Run as a Uvicorn server."""

    exit_code = 0
    try:
        pyroscope.configure(
            application_name="fastapi-sample",
            server_address=PYROSCOPE_ENDPOINT,  # See https://grafana.com/docs/pyroscope/next/configure-client/language-sdks/python/
            # server_port=EXPOSE_PORT,
            # service_name="fastapi-sample",
            # trace_id_key="otelTraceID",
            # span_id_key="otelSpanID",
            sample_rate=100,  # default is 100
        )

        setup_logging()
        # update uvicorn access logger format
        # log_config = uvicorn.config.LOGGING_CONFIG
        # log_config["formatters"]["access"]["fmt"] = (
        #    "%(asctime)s %(levelname)s [%(name)s] [%(filename)s:%(lineno)d] [trace_id=%(otelTraceID)s span_id=%(otelSpanID)s resource.service.name=%(otelServiceName)s] - %(message)s"
        # )

        # log_config = None
        config = uvicorn.Config(
            app,
            host=EXPOSE_HOST,
            port=EXPOSE_PORT,
            # log_config=log_config,
        )
        server = uvicorn.Server(config)
        server.run()
    except AttributeError as e:
        logging.error(f"API port is missing from the settings: {e}")
        exit_code = 1
    finally:
        exit(exit_code)


if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    uvicorn_run()
