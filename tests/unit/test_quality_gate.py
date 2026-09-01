"""Behavioral tests for the canonical publication quality gate."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "quality-gate.sh"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _initialize_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.email", "quality-gate@example.invalid")
    _git(repo, "config", "user.name", "Quality Gate Test")
    (repo / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    (repo / "tracked.txt").write_text("first\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "tracked.txt")
    _git(repo, "commit", "--quiet", "-m", "test: initial")


def _install_pre_commit_stub(repo: Path, marker: Path) -> None:
    executable = repo / ".venv" / "bin" / "pre-commit"
    executable.parent.mkdir(parents=True)
    executable.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf "%s\\n" "$*" >> "${QUALITY_GATE_MARKER}"\n',
        encoding="utf-8",
    )
    executable.chmod(0o755)
    marker.unlink(missing_ok=True)


def _run_gate(
    repo: Path,
    *,
    marker: Path,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["QUALITY_GATE_MARKER"] = str(marker)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(GATE)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_quality_gate_chooses_closest_remote_default_ref(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    marker = tmp_path / "pre-commit.log"
    _initialize_repo(repo)
    main_sha = _git(repo, "rev-parse", "HEAD")

    (repo / "tracked.txt").write_text("first\nsecond\n", encoding="utf-8")
    _git(repo, "commit", "--quiet", "-am", "test: master baseline")
    master_sha = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/remotes/origin/main", main_sha)
    _git(repo, "update-ref", "refs/remotes/origin/master", master_sha)
    _git(repo, "switch", "--quiet", "-c", "feature")

    (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
    _git(repo, "add", "feature.txt")
    _git(repo, "commit", "--quiet", "-m", "test: feature")
    _install_pre_commit_stub(repo, marker)

    result = _run_gate(repo, marker=marker)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Comparing changed files against origin/master" in result.stdout
    assert marker.read_text(encoding="utf-8").startswith("run --hook-stage pre-commit")


def test_quality_gate_rejects_invalid_explicit_base_ref(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    marker = tmp_path / "pre-commit.log"
    _initialize_repo(repo)
    _install_pre_commit_stub(repo, marker)

    result = _run_gate(
        repo,
        marker=marker,
        extra_env={"QUALITY_BASE_REF": "origin/does-not-exist"},
    )

    assert result.returncode == 2
    assert "QUALITY_BASE_REF does not resolve to a commit" in result.stderr
    assert not marker.exists()


def test_quality_gate_requires_a_git_worktree(tmp_path: Path) -> None:
    marker = tmp_path / "pre-commit.log"

    result = _run_gate(tmp_path, marker=marker)

    assert result.returncode == 2
    assert "must run inside a Git working tree" in result.stdout
    assert not marker.exists()
