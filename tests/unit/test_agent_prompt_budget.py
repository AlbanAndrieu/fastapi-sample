"""Guard the always-loaded agent prompt budget and single-source profile policy."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_agent_policy_is_compact_and_preserves_hard_gates() -> None:
    policy = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert len(policy.encode("utf-8")) <= 8000
    for required in (
        "## Mandatory execution protocol",
        "### Skill routing",
        "no-GitHub-Actions/no-credit mode",
        "scripts/agent-quality-gate.sh --fix",
        "scripts/agent-publish.sh",
        "must not declare work complete",
        "next acceptance proof",
        "FASTAPI_AGENT_PROFILE=workstation",
        "Codex",
    ):
        assert required in policy


def test_claude_adapter_and_selected_skills_are_bounded() -> None:
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "@AGENTS.md" in claude
    assert len(claude.splitlines()) <= 35
    for skill in ("local-first-quality", "homelab-runtime-status"):
        content = (ROOT / ".agents/skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        assert len(content.encode("utf-8")) <= 4800
        assert "docs/engineering-roadmap.md" in content
        assert "NOT_RUN" in content


def test_original_instructions_remain_archived_not_duplicated_at_entrypoint() -> None:
    for name in (
        "2026-11-14-agent-guide-before-profiles.md",
        "2026-11-14-local-first-quality-before-profiles.md",
        "2026-11-14-homelab-runtime-status-before-profiles.md",
    ):
        assert (ROOT / "docs/archive" / name).is_file()
    assert (ROOT / ".claude/skills").is_symlink()
