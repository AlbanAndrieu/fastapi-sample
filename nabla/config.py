""" Settings for nabla project """
from functools import lru_cache
from pathlib import Path

from pydantic import BaseSettings


# Basic db & ovh settings
class Settings(BaseSettings):
    # db settings
    db_host: str = "localhost"
    db_name: str = "back"
    db_user: str = "back"
    db_password: str = "back"
    db_port: int = 5432

    # s3 settings
    ovh_username: str = "username"
    ovh_password: str = "password"
    ovh_project_name: str = "123456789"
    ovh_container: str = "nabla_models"

    # mlflow settings
    mlflow_s3_endpoint_url = "https://s3.gra.cloud.ovh.net"
    mlflow_tracking_uri: str = "https://mlflow.jusmundi.com/"

    class Config:
        env_file = Path(__file__).parent.parent.absolute() / ".env"


@lru_cache()
def get_settings():
    """
    Return Settings object as a dependency and use @lru_cache
    decorator to create object and load .env file only once
    """
    return Settings()


# Logging
LOG_FORMAT = "[%(asctime)s] [%(process)d] [%(name)s] [%(levelname)s] %(message)s"
LOGGING_CONFIG = {
    "version": 1,
    ""
    "formatters": {
        "standard": {
            "format": LOG_FORMAT,
            "datefmt": "%Y-%m-%d %H:%M:%S %z",
        },
    },
    "handlers": {
        "default": {
            "level": "INFO",
            "formatter": "standard",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",  # Default is stderr
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "standard",
            "filename": Path(__file__).parent.parent.absolute() / "var/local_logs.log",
            "maxBytes": 1048576,
            "backupCount": 3,
            "mode": "a",
        },
    },
    "loggers": {
        "": {  # root logger
            "handlers": ["default", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "nabla": {
            "handlers": ["default", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn": {
            "handlers": ["default", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
