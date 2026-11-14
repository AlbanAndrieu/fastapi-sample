"""Offline, value-blind policy regression; no GitHub or runtime requests."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pr_reuse_rebase_and_batch_contract():
    policy = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for marker in (
        "Reuse an existing compatible open PR",
        "Synchronize before editing",
        "--force-with-lease",
        "Batch changes",
        "production stability",
        "completed cross-service migration",
        "Never auto-merge",
        "NOT_RUN",
    ):
        assert marker in policy


def test_skill_points_to_conditional_runbook():
    skill = (ROOT / ".agents/skills/local-first-quality/SKILL.md").read_text(
        encoding="utf-8"
    )
    detail = (ROOT / "docs/agent-execution-playbook.md").read_text(
        encoding="utf-8"
    )
    assert "PR ownership and batching" in skill
    assert "Working in an existing PR" in detail
    assert "H05/F03/F09" in detail
    assert "security checks" in detail or "security controls" in skill
