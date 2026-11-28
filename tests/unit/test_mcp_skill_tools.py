"""MCP tools carry their skill: Open WebUI only calls tools, never MCP prompts."""

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from nabla.api import v2
from nabla.api.users import me
from server_app import app


@pytest.mark.asyncio
async def test_mcp_lists_skill_tools_and_searxng_not_brave_or_google() -> None:
    async with Client(app.state.mcp) as client:
        names = {tool.name for tool in await client.list_tools()}

    assert {"search_alban_profile", "search_bababou", "triage_homelab_rss", "searxng", "tavily"} <= names
    assert not {"brave", "google"} & names


@pytest.mark.parametrize(
    ("path", "context_fn", "skill"),
    [("/v2/profile/search", "search_alban_profile_context", "profile-research"), ("/v2/bababou/search", "search_bababou_context", "bababou-lawyer")],
)
def test_search_tools_put_their_skill_before_the_context(monkeypatch: pytest.MonkeyPatch, path: str, context_fn: str, skill: str) -> None:
    monkeypatch.setattr(v2, context_fn, lambda question: f"CONTEXT for {question}")

    res = TestClient(app).get(path, params={"user_question": "who?"})

    assert res.status_code == 200
    head, context = res.json().split("\n\n---\n\n", 1)
    assert head.startswith(f"Instructions (skill {skill})")
    assert "name:" not in head  # frontmatter stays out of the model's instructions
    assert context == "CONTEXT for who?"


def test_bababou_tool_answers_as_a_family_law_attorney(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v2, "search_bababou_context", lambda question: "")

    text = TestClient(app).get("/v2/bababou/search", params={"user_question": "Bababou"}).json()

    assert "attorney" in text
    assert "Hague" in text
    assert "Never invent case law" in text


def test_rss_triage_is_truenas_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nabla.api.runtime_environment.homelab_runtime_detected", lambda: False)

    res = TestClient(app).get("/v2/rss/triage")

    assert res.status_code == 503
    assert res.json()["detail"] == "RSS triage is TrueNAS-only"


def test_rss_triage_returns_skill_technologies_and_articles(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_inputs() -> tuple[str, list[str], list[dict[str, str]]]:
        return "sha256:" + "0" * 64, ["redis", "traefik"], [{"id": "a" * 64, "title": "Redis 8.8 CVE", "summary": "s"}]

    monkeypatch.setattr("nabla.integrations.rss_relevance_live.triage_inputs", fake_inputs)

    body = TestClient(app).get("/v2/rss/triage").json()

    assert body["instructions"].startswith("# RSS triage for the homelab")
    assert body["technologies"] == ["redis", "traefik"]
    assert body["articles"][0]["title"] == "Redis 8.8 CVE"


def test_resume_text_keeps_visible_items_and_drops_contact_details() -> None:
    data = {
        "basics": {"name": "Alban Andrieu", "headline": "Cloud Architect", "email": "x@example.com", "phone": "+33 6"},
        "summary": {"content": "<p><strong>20 years</strong> of cloud</p>"},
        "sections": {
            "experience": {
                "hidden": False,
                "items": [{"id": "1", "hidden": False, "company": "Jus Mundi", "description": "<ul><li>AI</li></ul>"}, {"id": "2", "hidden": True, "company": "Hidden"}],
            },
            "skills": {"hidden": False, "items": [{"id": "3", "hidden": False, "name": "AI", "keywords": ["GPU", "LLM"], "level": 4}]},
            "awards": {"hidden": True, "items": [{"id": "4", "hidden": False, "title": "Secret"}]},
        },
    }

    text = me._resume_text(data)

    assert text.splitlines() == [
        "name: Alban Andrieu, headline: Cloud Architect",
        "20 years of cloud",
        "experience — company: Jus Mundi; description: AI",
        "skills — name: AI; keywords: GPU, LLM",
    ]
