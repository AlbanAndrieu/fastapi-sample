"""
This is the main interface.


to run this program:
1. activate virtual environment, see README.md for instructions
2. run: `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
"""

from nabla.fastapi_server import app, mcp  # noqa: F401

# We need to load as soon as possible the setup_loggers
from nabla.utils.log_config import setup_logging

setup_logging()

# Run the MCP server
if __name__ == "__main__":
    mcp.run()
