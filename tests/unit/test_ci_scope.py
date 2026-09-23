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


def _repo(tmp_path: Path) -> str:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "scope@example.invalid")
    _git(tmp_path, "config", "user.name", "Scope Test")
    return _commit_file(tmp_path, "README.txt", "base\n", "base")


def _scope(cwd: Path, base: str, head: str = "HEAD") -> dict[str, str]:
    output = _run(cwd, "bash", str(SCRIPT), base, head).stdout
    return dict(line.split("=", maxsplit=1) for line in output.splitlines())


def _mode(cwd: Path, base: str) -> str:
    return _run(cwd, "bash", str(SCRIPT), "--mode-only", base).stdout.strip()


def test_docs_only_scope_is_none(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _commit_file(tmp_path, "docs/quality.md", "docs\n", "docs")

    scope = _scope(tmp_path, base)
    assert scope == {
        "maintenance_only": "true",
        "application": "false",
        "sast": "false",
        "build": "false",
        "dependencies": "false",
        "dependency_mode": "none",
        "changed_count": "1",
    }
    assert _mode(tmp_path, base) == "none"


def test_quality_infrastructure_scope_is_quality(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _commit_file(
        tmp_path,
        "scripts/quality-gate.sh",
        "#!/usr/bin/env bash\nexit 0\n",
        "quality",
    )

    scope = _scope(tmp_path, base)
    assert scope["maintenance_only"] == "true"
    assert scope["sast"] == "false"
    assert scope["build"] == "false"
    assert scope["dependencies"] == "false"
    assert scope["dependency_mode"] == "quality"


def test_workflow_change_keeps_sast_without_application_build(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _commit_file(
        tmp_path,
        ".github/workflows/python.yml",
        "name: Python\n",
        "workflow",
    )

    scope = _scope(tmp_path, base)
    assert scope["maintenance_only"] == "false"
    assert scope["application"] == "false"
    assert scope["sast"] == "true"
    assert scope["build"] == "false"
    assert scope["dependencies"] == "false"
    assert scope["dependency_mode"] == "quality"


def test_application_scope_is_fail_closed_full(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _commit_file(tmp_path, "nabla/api/example.py", "VALUE = 1\n", "application")

    scope = _scope(tmp_path, base)
    assert scope["maintenance_only"] == "false"
    assert scope["application"] == "true"
    assert scope["sast"] == "true"
    assert scope["build"] == "true"
    assert scope["dependencies"] == "true"
    assert scope["dependency_mode"] == "full"


def test_application_test_keeps_dependencies_without_build(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _commit_file(
        tmp_path,
        "tests/unit/test_runtime.py",
        "def test_runtime():\n    assert True\n",
        "test",
    )

    scope = _scope(tmp_path, base)
    assert scope["application"] == "false"
    assert scope["sast"] == "true"
    assert scope["build"] == "false"
    assert scope["dependencies"] == "true"
    assert scope["dependency_mode"] == "full"


def test_unknown_path_fails_closed_to_full(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _commit_file(tmp_path, "config/runtime-policy.json", "{}\n", "unknown")

    assert _mode(tmp_path, base) == "full"


def test_empty_diff_fails_closed_to_full(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    scope = _scope(tmp_path, base, base)

    assert scope["maintenance_only"] == "false"
    assert scope["application"] == "true"
    assert scope["sast"] == "true"
    assert scope["build"] == "true"
    assert scope["dependencies"] == "true"
    assert scope["dependency_mode"] == "full"
    assert scope["changed_count"] == "0"


def test_uncommitted_application_work_fails_closed_locally(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _commit_file(tmp_path, "docs/quality.md", "docs\n", "docs")
    target = tmp_path / "nabla/api/uncommitted.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 2\n", encoding="utf-8")

    scope = _scope(tmp_path, base)
    assert scope["application"] == "true"
    assert scope["sast"] == "true"
    assert scope["build"] == "true"
    assert scope["dependencies"] == "true"
    assert scope["dependency_mode"] == "full"


def test_classifier_writes_all_github_outputs(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _commit_file(
        tmp_path,
        ".github/workflows/python.yml",
        "name: Python\n",
        "workflow",
    )
    output = tmp_path / "github-output.txt"
    env = {**os.environ, "GITHUB_OUTPUT": str(output)}

    _run(tmp_path, "bash", str(SCRIPT), base, "HEAD", env=env)

    payload = output.read_text(encoding="utf-8")
    for expected in (
        "maintenance_only=false",
        "application=false",
        "sast=true",
        "build=false",
        "dependencies=false",
        "dependency_mode=quality",
        "changed_count=1",
    ):
        assert expected in payload
