from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from nabla.version import API_VERSION, RELEASE_VERSION

# logger = logging.getLogger(__name__)
# logger.setLevel(logging.INFO)

router = APIRouter(prefix="/v2")


@router.get("/version", operation_id="get_mcp_info")
def api_version(request: Request) -> dict[str, object]:
    """Return application version and MCP integration metadata for tool clients such as OpenWebUI."""
    return {
        "version": request.app.version,
        "api_version": API_VERSION,
        "release_version": RELEASE_VERSION,
        "service": "fastapi-sample",
        "mcp": {
            "transport": "streamable-http",
            "endpoint": "/llm/mcp/",
            "openapi_endpoint": "/openapi.json",
            "api_ui": "/api",
        },
        "knowledge": {
            "alban_profile": "https://www.albanandrieu.com/",
            "linkedin": "https://www.linkedin.com/in/nabla/",
            "openrag": "optional; available when the openrag MCP client is configured and enabled",
        },
        "usage": {
            "mcp_entrypoint_questions": "Use this tool to describe the MCP endpoint and integration metadata.",
            "alban_profile_questions": (
                "Prefer a dedicated profile tool when available; otherwise search albanandrieu.com "
                "with an exposed web-search tool."
            ),
        },
    }


@router.get("/ping")
def ping():
    """
    Healthcheck endpoint.
    """
    return JSONResponse({"ping": "pong v2!"})
