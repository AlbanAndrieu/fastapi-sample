"""Reviewed SKILL.md files shared by the ``/run`` deep agent and the MCP tools."""

from pathlib import Path

SKILLS_DIR = Path(__file__).with_name("skills")


def skill_instructions(name: str) -> str:
    """Return a skill's body without its frontmatter.

    MCP clients such as Open WebUI only call tools, so each tool result carries
    the instructions its answer must follow.
    """
    text = (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
    return text.split("---", 2)[2].strip()
