"""Reviewed skills injected per request into the /run Deep Agent."""

from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from nabla.deepagents import workflow as wf
from nabla.main import app


@pytest.fixture(autouse=True)
def clear_workflow_caches() -> None:
    wf._get_workflow_llm.cache_clear()
    wf._build_workflow_agent.cache_clear()
    yield
    wf._get_workflow_llm.cache_clear()
    wf._build_workflow_agent.cache_clear()


def test_shipped_skills_have_matching_frontmatter() -> None:
    assert {"profile-research", "bababou-research"} <= wf.available_skills()
    for name in wf.available_skills():
        text = (wf._SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
        front = yaml.safe_load(text.split("---", 2)[1])
        assert front["name"] == name
        assert 0 < len(front["description"]) <= 1024


def test_run_forwards_only_reviewed_skill_names(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, ...]] = []

    def fake_safe_invoke(message: str, skills: tuple[str, ...] = ()) -> str:
        seen.append(skills)
        return "ok"

    monkeypatch.setattr(wf, "safe_invoke_llm", fake_safe_invoke)
    client = TestClient(app)
    res = client.post("/run", json={"user_input": "Tell me about bababou", "skills": ["bababou-research", "bababou-research"]})
    assert res.status_code == 200
    assert seen == [("bababou-research",)]


@pytest.mark.parametrize("skills", [["unknown-skill"], ["../../etc/passwd"], ["Profile-Research"], ["a", "b", "c", "d"]])
def test_run_rejects_unreviewed_skills(monkeypatch: pytest.MonkeyPatch, skills: list[str]) -> None:
    monkeypatch.setattr(wf, "safe_invoke_llm", lambda *_args, **_kwargs: pytest.fail("LLM must not run"))
    res = TestClient(app).post("/run", json={"user_input": "hello", "skills": skills})
    assert res.status_code == 422


class _CapturingModel(GenericFakeChatModel):
    """Fake chat model that records the system prompt the agent sends."""

    system_prompts: list[str] = []

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_CapturingModel":
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.system_prompts.append("\n".join(str(m.content) for m in messages if m.type == "system"))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def test_selected_skill_reaches_the_model_system_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _CapturingModel(messages=iter([AIMessage(content="first"), AIMessage(content="second")]))
    model.system_prompts = []
    monkeypatch.setattr(wf, "_get_workflow_llm", lambda: model)
    monkeypatch.setattr(wf, "build_openrag_mcp_tools", list)
    assert wf._invoke_agent("Who is Bababou?", ("bababou-research",)) == "first"
    assert "bababou-research" in model.system_prompts[-1]
    assert wf._invoke_agent("Who is Bababou?") == "second"
    assert "bababou-research" not in model.system_prompts[-1]
