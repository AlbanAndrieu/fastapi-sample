"""Offline regression contracts for the GitHub Actions Draft cost boundary."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts/ci/check_draft_workflows.py"


def _invoke(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), str(root)],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )


def _workflow(directory: Path, *, guard: bool = True, review: bool = True) -> None:
    workflow_dir = directory / ".github/workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    (workflow_dir / "test.yml").write_text(
        "name: test\non:\n  pull_request:\n"
        + ("    types: [opened, synchronize, ready_for_review]\n" if review else "    types: [opened, synchronize]\n")
        + "jobs:\n  check:\n"
        + ("    if: github.event_name != 'pull_request' || github.event.pull_request.draft == false\n" if guard else "")
        + "    runs-on: ubuntu-latest\n    steps:\n      - run: echo check\n",
        encoding="utf-8",
    )


def test_all_current_pr_workflows_guard_draft_runners() -> None:
    result = _invoke(ROOT)
    assert result.returncode == 0, result.stderr
    assert "DRAFT_GUARD_OK" in result.stdout


def test_missing_draft_guard_fails_closed(tmp_path: Path) -> None:
    _workflow(tmp_path, guard=False)
    result = _invoke(tmp_path)
    assert result.returncode == 1
    assert "missing draft PR guard" in result.stderr


def test_review_transition_is_required(tmp_path: Path) -> None:
    _workflow(tmp_path, review=False)
    result = _invoke(tmp_path)
    assert result.returncode == 1
    assert "missing ready_for_review" in result.stderr


def test_missing_workflows_are_not_success(tmp_path: Path) -> None:
    result = _invoke(tmp_path)
    assert result.returncode == 1
    assert "no pull_request workflows found" in result.stderr


def _job_with_if(directory: Path, condition: str) -> None:
    workflow_dir = directory / ".github/workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    (workflow_dir / "test.yml").write_text(
        "name: test\non:\n  pull_request:\n    types: [opened, ready_for_review]\n"
        f"jobs:\n  post-deploy:\n    if: {condition}\n"
        "    runs-on: ubuntu-latest\n    steps:\n      - run: echo check\n",
        encoding="utf-8",
    )


def test_job_that_never_runs_on_pull_request_needs_no_draft_guard(tmp_path: Path) -> None:
    _job_with_if(tmp_path, "${{ github.event_name != 'pull_request' }}")
    assert _invoke(tmp_path).returncode == 0


def test_never_pr_guard_cannot_be_widened_with_or(tmp_path: Path) -> None:
    _job_with_if(tmp_path, "${{ github.event_name != 'pull_request' || github.event.action == 'opened' }}")
    result = _invoke(tmp_path)
    assert result.returncode == 1
    assert "missing draft PR guard" in result.stderr
