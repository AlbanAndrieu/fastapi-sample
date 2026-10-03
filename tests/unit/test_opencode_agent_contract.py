"""Contracts for the repository-local OpenCode agent workflow."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_opencode_uses_repository_maintainer_and_native_skills() -> None:
    config = json.loads((ROOT / "opencode.json").read_text(encoding="utf-8"))

    assert config["default_agent"] == "fastapi-maintainer"
    assert config["permission"]["skill"]["*"] == "allow"
    assert config["instructions"] == ["AGENTS.md"]
    assert config["tool_output"] == {"max_lines": 600, "max_bytes": 32000}
    assert config["compaction"] == {"auto": True, "prune": True, "tail_turns": 6}

    github = config["mcp"]["github"]
    assert github["type"] == "local"
    assert "--read-only" in github["command"]


def test_opencode_maintainer_delegates_to_canonical_policy() -> None:
    agent = (ROOT / ".opencode" / "agents" / "fastapi-maintainer.md").read_text(
        encoding="utf-8",
    )

    assert "mode: primary" in agent
    assert "steps: 40" in agent
    assert "model:" not in agent.split("---", 2)[1]
    assert "AGENTS.md" in agent
    assert "docs/engineering-roadmap.md" in agent
    assert ".opencode/commands/" in agent
    assert "[skip ci]" in agent
    assert len(agent.splitlines()) <= 35



def test_global_agent_adapters_are_thin_and_delegate_to_agents_policy() -> None:
    adapters = (
        ROOT / "CLAUDE.md",
        ROOT / ".github" / "copilot-instructions.md",
        ROOT / ".cursor" / "rules" / "001_project-description.mdc",
        ROOT / ".opencode" / "agents" / "fastapi-maintainer.md",
    )

    for adapter in adapters:
        text = adapter.read_text(encoding="utf-8")
        assert "AGENTS.md" in text
        assert len(text.splitlines()) <= 35

    cursor_rules = ROOT / ".cursor" / "rules"
    always_on = []
    for rule in cursor_rules.glob("*.mdc"):
        text = rule.read_text(encoding="utf-8")
        if "alwaysApply: true" in text:
            always_on.append(rule.name)

    assert always_on == ["001_project-description.mdc"]


def test_obsolete_global_cursor_rules_are_removed_or_scoped() -> None:
    rules = ROOT / ".cursor" / "rules"

    for removed in (
        "001_workspace.mdc",
        "003_project-tooling.mdc",
        "100_general-style.mdc",
        "130_version-control_git.mdc",
        "301_memory.mdc",
        "302_artifacts.mdc",
    ):
        assert not (rules / removed).exists()

    katex = (rules / "111_katex-math.mdc").read_text(encoding="utf-8")
    assert "alwaysApply: false" in katex


def test_opencode_reviewer_is_read_only() -> None:
    reviewer = (ROOT / ".opencode" / "agents" / "quality-reviewer.md").read_text(encoding="utf-8")

    assert "mode: subagent" in reviewer
    assert "steps: 12" in reviewer
    assert "edit: deny" in reviewer
    assert "'*': deny" in reviewer
    assert "git status*: allow" in reviewer
    assert "git diff*: allow" in reviewer
    assert "git log*: allow" in reviewer
    assert "git show*: allow" in reviewer


def test_opencode_commands_cover_local_agent_workflow() -> None:
    commands = ROOT / ".opencode" / "commands"

    roadmap = (commands / "roadmap-next.md").read_text(encoding="utf-8")
    quality = (commands / "quality-fix.md").read_text(encoding="utf-8")
    publish = (commands / "publish-local.md").read_text(encoding="utf-8")
    review = (commands / "review-local.md").read_text(encoding="utf-8")

    assert "agent: fastapi-maintainer" in roadmap
    assert "outil `skill`" in roadmap
    assert "scripts/agent-quality-gate.sh --fix" in quality
    assert "scripts/agent-publish.sh" in publish
    assert "agent: quality-reviewer" in review
    assert "git diff --check" in review


def test_all_repository_skills_use_exact_discovery_filename() -> None:
    skills = ROOT / ".agents" / "skills"
    malformed = [path for path in skills.rglob("SKILL*") if path.is_file() and path.name != "SKILL.md"]

    assert malformed == []


def test_agents_policy_exposes_deterministic_small_model_protocol() -> None:
    policy = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "## Mandatory execution protocol" in policy
    assert "### Skill routing" in policy
    assert "scripts/agent-quality-gate.sh --fix" in policy
    assert "scripts/agent-publish.sh" in policy
    assert "scripts/quality-gate.sh --publish" not in policy
    assert "no-GitHub-Actions/no-credit mode" in policy
