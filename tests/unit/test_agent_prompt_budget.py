"""Guard the single-source agent instruction budget after PR #434."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_root_policy_budget_and_security_contract() -> None:
    policy = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert len(policy.encode("utf-8")) <= 8000
    for required in (
        "## Mandatory execution protocol",
        "Une worktree Git par agent",
        "QUALITY_PYTEST_MAXFAIL=0",
        "L2",
        "L3",
        "must not declare work complete",
        "AGENT_EXECUTION_MODE=workstation",
        "H05",
    ):
        assert required in policy


def test_claude_adapter_and_skills_are_loaded_only_when_relevant() -> None:
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "@AGENTS.md" in claude
    assert len(claude.splitlines()) <= 20
    for skill in ("local-first-quality", "homelab-runtime-status"):
        contents = (ROOT / ".agents/skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        assert len(contents.encode("utf-8")) <= 4000
        assert "NOT_RUN" in contents
    assert (ROOT / "docs/agent-execution-playbook.md").is_file()
