"""Behavioral tests for the agent quality dependency-mode classifier."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "agent-quality-gate.sh"


def _run(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        list(args),
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _git(cwd: Path, *args: str) -> str:
    return _run(cwd, "git", *args)


def _commit_file(cwd: Path, path: str, content: str, message: str) -> str:
    target = cwd / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(cwd, "add", path)
    _git(cwd, "commit", "-m", message)
    return _git(cwd, "rev-parse", "HEAD")


def _dependency_mode(cwd: Path, base: str) -> str:
    env = {**os.environ, "QUALITY_BASE_REF": base}
    return _run(cwd, "bash", str(SCRIPT), "--dependency-mode", env=env)


def test_dependency_mode_keeps_quality_contract_changes_isolated(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "scope@example.invalid")
    _git(tmp_path, "config", "user.name", "Scope Test")
    base = _commit_file(tmp_path, "README.md", "base\n", "base")

    _commit_file(
        tmp_path,
        "tests/unit/test_agent_publication_proof.py",
        "def test_placeholder():\n    assert True\n",
        "quality test",
    )
    assert _dependency_mode(tmp_path, base) == "quality"


def test_dependency_mode_uses_full_scope_for_application_python(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "scope@example.invalid")
    _git(tmp_path, "config", "user.name", "Scope Test")
    base = _commit_file(tmp_path, "README.md", "base\n", "base")

    _commit_file(
        tmp_path,
        "nabla/api/example.py",
        "VALUE = 1\n",
        "application",
    )
    assert _dependency_mode(tmp_path, base) == "full"


def test_dependency_mode_skips_docs_only_changes(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "scope@example.invalid")
    _git(tmp_path, "config", "user.name", "Scope Test")
    base = _commit_file(tmp_path, "README.md", "base\n", "base")

    _commit_file(tmp_path, "docs/quality.md", "docs\n", "docs")
    assert _dependency_mode(tmp_path, base) == "none"
