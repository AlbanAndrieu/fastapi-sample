"""
This is the main interface.


to run this program:
1. activate virtual environment, see README.md for instructions
2. run: `fastmcp run server-mcp.py`
"""
# from nabla.fastapi_server import mcp
from fastmcp import FastMCP

# We need to load as soon as possible the setup_loggers
from nabla.utils.log_config import setup_logging

setup_logging()

mcp = FastMCP("Demo 🚀")

@mcp.tool
def hello(name: str) -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
  # mcp.run(transport="stdio")  # Default, so transport argument is optional
  mcp.run(transport="http", host="127.0.0.1", port=8000, path="/mcp") # Streamable HTTP: Recommended for web deployments.
  # mcp.run(transport="sse", host="127.0.0.1", port=8000) # SSE: For compatibility with existing SSE clients.
