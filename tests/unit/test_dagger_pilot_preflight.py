"""Offline tests for the fail-closed Dagger pilot prerequisite checker."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = ROOT / "scripts" / "dagger-pilot-preflight.sh"


def test_preflight_refuses_missing_module_without_running_dagger(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    result = subprocess.run(
        ["bash", str(PREFLIGHT)],
        cwd=repo,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "NOT READY" in result.stderr
    assert "READY FOR MANUAL PILOT" not in result.stdout


def test_preflight_is_non_mutating() -> None:
    script = PREFLIGHT.read_text(encoding="utf-8")
    assert "dagger call" not in script
    assert "docker run" not in script
    assert "git fetch" not in script
    assert "dagger.lock" in script
    assert "git rev-parse HEAD" in script


def test_preflight_requires_tracked_inputs(tmp_path: Path) -> None:
    """A local generated lockfile must not masquerade as reviewed parity input."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("uv", "just", "dagger", "docker"):
        executable = fake_bin / name
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
    }
    (repo / "dagger.json").write_text("{}\n", encoding="utf-8")
    (repo / "dagger.lock").write_text("{}\n", encoding="utf-8")

    def check() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(PREFLIGHT)],
            cwd=repo,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    untracked = check()
    assert untracked.returncode == 2
    assert "must be tracked in Git" in untracked.stderr

    subprocess.run(
        ["git", "-C", str(repo), "add", "dagger.json", "dagger.lock"],
        check=True,
    )
    subprocess.run(
        [
            "git", "-C", str(repo),
            "-c", "user.name=Test",
            "-c", "user.email=test@example.org",
            "commit", "-qm", "fixture",
        ],
        check=True,
    )
    tracked = check()
    assert tracked.returncode == 0, tracked.stderr
    assert "READY FOR MANUAL PILOT" in tracked.stdout
