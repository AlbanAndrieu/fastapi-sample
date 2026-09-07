import argparse
import logging

import uvicorn.config
from pydantic import ValidationError

from nabla.config_settings import EXPOSE_HOST, EXPOSE_PORT, get_settings
from nabla.main import app
from nabla.utils.log_config import setup_logging

logger = logging.getLogger(__name__)
logger.level = logging.INFO


def uvicorn_run() -> None:
    """Run as a Uvicorn server."""

    exit_code = 0
    try:
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
    uvicorn_run()


parser = argparse.ArgumentParser(prog="server_app")
parser.add_argument("echo", help="String to print back to the console")

if __name__ == "__main__":
    args = parser.parse_args()
    print(args.echo)
    main()
