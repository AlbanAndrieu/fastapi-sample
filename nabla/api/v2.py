import os

import httpx
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import JSONResponse

from nabla.api.users.bababou import search_bababou_context
from nabla.api.users.me import search_alban_profile_context
from nabla.deepagents.skill_files import skill_instructions
from nabla.version import API_VERSION, BUILD_REVISION, RELEASE_VERSION

router = APIRouter(prefix="/v2")


@router.get("/version", operation_id="get_mcp_info")
def api_version(request: Request) -> dict[str, object]:
    """Return application version and MCP integration metadata for tool clients such as OpenWebUI."""
    return {
        "version": request.app.version,
        "api_version": API_VERSION,
        "release_version": RELEASE_VERSION,
        "build_revision": BUILD_REVISION or None,
        # F01 owner decision (21/11): FastAPI Cloud provides no Git SHA; correlate by its deployment id.
        "deployment_id": os.getenv("FASTAPICLOUD_DEPLOYMENT_ID", "").strip() or None,
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
            "bababou_questions": "Use search_bababou with the user's question; answer as a family-law attorney.",
            "rss_questions": "Use triage_homelab_rss to sort FreshRSS articles by homelab relevance (TrueNAS only).",
        },
    }


def _with_skill(name: str, context: str) -> str:
    return f"Instructions (skill {name}), follow them for this answer:\n\n{skill_instructions(name)}\n\n---\n\n{context}"


@router.get("/profile/search", operation_id="search_alban_profile")
def search_alban_profile(user_question: str) -> str:
    """Search Alban Andrieu's website, LinkedIn and Reactive Resume CV for OpenWebUI/MCP clients.

    The result starts with the profile-research skill the answer must follow.
    """
    return _with_skill("profile-research", search_alban_profile_context(user_question))


@router.get("/bababou/search", operation_id="search_bababou")
def search_bababou(user_question: str) -> str:
    """Load bababou.com context about Éléonore (Bababou) for OpenWebUI/MCP clients.

    Call it for any question about Bababou or her legal situation (child abduction,
    parental alienation). The result starts with the bababou-lawyer skill: answer as
    Alban's family-law attorney.
    """
    return _with_skill("bababou-lawyer", search_bababou_context(user_question))


@router.get("/rss/triage", operation_id="triage_homelab_rss")
async def triage_homelab_rss() -> dict[str, object]:
    """Newest FreshRSS articles plus the homelab catalog technologies to sort them by (TrueNAS only).

    Follow ``instructions`` (rss-triage skill) to rank the articles. No LLM runs server-side.
    """
    from nabla.integrations.rss_relevance_live import triage_inputs  # noqa: PLC0415 -- TrueNAS-only path

    try:
        revision, technologies, articles = await triage_inputs()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="FreshRSS request failed") from exc
    return {"instructions": skill_instructions("rss-triage"), "catalogRevision": revision, "technologies": technologies, "articles": articles}


@router.get("/ping")
def ping():
    """Healthcheck endpoint."""
    return JSONResponse({"ping": "pong v2!"})
