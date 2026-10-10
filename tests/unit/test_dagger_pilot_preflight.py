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
