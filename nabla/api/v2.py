from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from nabla.api.users.me import search_alban_profile_context
from nabla.version import API_VERSION, RELEASE_VERSION

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
            "endpoint": "/mcp",
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
            "alban_profile_questions": "Use search_alban_profile with the user's question.",
        },
    }


@router.get("/profile/search", operation_id="search_alban_profile")
def search_alban_profile(user_question: str) -> str:
    """Search verified public context about Alban Andrieu for OpenWebUI/MCP clients."""
    return search_alban_profile_context(user_question)


@router.get("/ping")
def ping():
    """Healthcheck endpoint."""
    return JSONResponse({"ping": "pong v2!"})
