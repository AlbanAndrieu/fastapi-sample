"""Behavioral tests for warning-only Python CI performance baselines."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci-performance-budget.sh"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _run(
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _repo(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "perf@example.invalid")
    _git(tmp_path, "config", "user.name", "Performance Baseline")
    (tmp_path / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "base")


def test_performance_baseline_is_non_blocking_without_thresholds(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    summary = tmp_path / "summary.md"
    env = {
        **os.environ,
        "GITHUB_STEP_SUMMARY": str(summary),
        "CI_DEPENDENCY_MODE": "full",
        "AGENT_GATE_SECONDS": "7",
        "UV_SYNC_SECONDS": "11",
        "PYTEST_SECONDS": "13",
        "UV_BUILD_SECONDS": "3",
        "VENV_MB": "420",
        "DIST_MB": "8",
    }

    result = _run(tmp_path, env)

    assert result.returncode == 0
    assert "CI_PERF_BASELINE schema=1" in result.stdout
    assert "scope=full" in result.stdout
    assert "uv_sync_s=11" in result.stdout
    assert "pytest_s=13" in result.stdout
    assert "baseline only; no warning threshold configured" in result.stdout
    assert "quality remains non-blocking" not in result.stderr
    assert "Python CI performance baseline" in summary.read_text(encoding="utf-8")


def test_exceeded_threshold_warns_without_failing(tmp_path: Path) -> None:
    _repo(tmp_path)
    env = {
        **os.environ,
        "AGENT_GATE_SECONDS": "11",
        "AGENT_GATE_WARN_SECONDS": "10",
    }

    result = _run(tmp_path, env)

    assert result.returncode == 0
    assert "::warning::CI performance regression candidate" in result.stdout
    assert "quality remains non-blocking" in result.stdout


def test_invalid_metric_warns_without_failing(tmp_path: Path) -> None:
    _repo(tmp_path)
    env = {
        **os.environ,
        "PYTEST_SECONDS": "not-a-number",
    }

    result = _run(tmp_path, env)

    assert result.returncode == 0
    assert "::warning::CI performance metric pytest is invalid" in result.stdout


def test_performance_budget_script_is_executable() -> None:
    assert SCRIPT.stat().st_mode & stat.S_IXUSR


def test_performance_budget_has_no_blocking_exit() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "CI_PERF_BASELINE schema=1" in text
    assert "warning thresholds are optional and disabled by default" in text
    assert "exit 1" not in text
