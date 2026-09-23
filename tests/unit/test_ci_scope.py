"""Behavioral tests for the centralized CI scope classifier."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci-scope.sh"


def _run(
    cwd: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _git(cwd: Path, *args: str) -> str:
    return _run(cwd, "git", *args).stdout.strip()


def _commit_file(cwd: Path, path: str, content: str, message: str) -> str:
    target = cwd / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(cwd, "add", path)
    _git(cwd, "commit", "-m", message)
    return _git(cwd, "rev-parse", "HEAD")


def _mode(cwd: Path, base: str) -> str:
    return _run(cwd, "bash", str(SCRIPT), "--mode-only", base).stdout.strip()


def _repo(tmp_path: Path) -> str:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "scope@example.invalid")
    _git(tmp_path, "config", "user.name", "Scope Test")
    return _commit_file(tmp_path, "README.md", "base\n", "base")


def test_docs_only_scope_is_none(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _commit_file(tmp_path, "docs/quality.md", "docs\n", "docs")

    assert _mode(tmp_path, base) == "none"


def test_quality_infrastructure_scope_is_quality(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _commit_file(
        tmp_path,
        "scripts/quality-gate.sh",
        "#!/usr/bin/env bash\nexit 0\n",
        "quality",
    )

    assert _mode(tmp_path, base) == "quality"


def test_application_scope_is_full(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _commit_file(tmp_path, "nabla/api/example.py", "VALUE = 1\n", "application")

    assert _mode(tmp_path, base) == "full"


def test_unknown_path_fails_closed_to_full(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _commit_file(tmp_path, "config/runtime-policy.json", "{}\n", "unknown")

    assert _mode(tmp_path, base) == "full"


def test_quality_plus_docs_remains_quality(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _commit_file(tmp_path, "docs/quality.md", "docs\n", "docs")
    _commit_file(
        tmp_path,
        "tests/unit/test_agent_quality_gate_contract.py",
        "def test_placeholder():\n    assert True\n",
        "quality",
    )

    assert _mode(tmp_path, base) == "quality"


def test_application_change_dominates_quality_change(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _commit_file(
        tmp_path,
        "scripts/quality-gate.sh",
        "#!/usr/bin/env bash\nexit 0\n",
        "quality",
    )
    _commit_file(tmp_path, "server_app.py", "app = object()\n", "application")

    assert _mode(tmp_path, base) == "full"


def test_classifier_writes_github_outputs(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _commit_file(
        tmp_path,
        "scripts/agent-publish.sh",
        "#!/usr/bin/env bash\nexit 0\n",
        "quality",
    )
    output = tmp_path / "github-output.txt"
    env = {**os.environ, "GITHUB_OUTPUT": str(output)}

    _run(tmp_path, "bash", str(SCRIPT), base, "HEAD", env=env)

    payload = output.read_text(encoding="utf-8")
    assert "dependency_mode=quality" in payload
    assert "changed_count=1" in payload
