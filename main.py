"""
This is the main interface.


to run this program:
1. activate virtual environment, see README.md for instructions
2. run: `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
"""

# We need to load as soon as possible the setup_loggers
from nabla.utils.log_config import setup_logging

setup_logging()

from nabla.fastapi_server import app  # noqa: E402, F401
