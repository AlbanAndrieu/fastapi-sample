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


def test_opencode_maintainer_uses_canonical_local_gates() -> None:
    agent = (
        ROOT / ".opencode" / "agents" / "fastapi-maintainer.md"
    ).read_text(encoding="utf-8")

    assert "mode: primary" in agent
    assert "steps: 40" in agent
    assert "scripts/agent-quality-gate.sh --fix" in agent
    assert "scripts/agent-publish.sh" in agent
    assert "docs/engineering-roadmap.md" in agent
    assert "outil `skill`" in agent
    assert "[skip ci]" in agent


def test_opencode_reviewer_is_read_only() -> None:
    reviewer = (
        ROOT / ".opencode" / "agents" / "quality-reviewer.md"
    ).read_text(encoding="utf-8")

    assert "mode: subagent" in reviewer
    assert "steps: 12" in reviewer
    assert "edit: deny" in reviewer
    assert "bash: deny" in reviewer


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
    malformed = [
        path
        for path in skills.rglob("SKILL*")
        if path.is_file() and path.name != "SKILL.md"
    ]

    assert malformed == []
