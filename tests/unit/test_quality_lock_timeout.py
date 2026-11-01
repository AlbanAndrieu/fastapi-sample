"""Regression tests for worktree locks and bounded local quality commands."""

from __future__ import annotations

import os
import shutil
import select
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "scripts/ci/quality-lock.sh"
DEADLINE = ROOT / "scripts/ci/quality-timeout.sh"


def _bash(source: Path, code: str, *, timeout: int = 5) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", 'source "$1"; shift; ' + code, "_", str(source)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def test_lock_rejects_contending_agent_and_releases_after_exit(tmp_path: Path) -> None:
    if shutil.which("flock") is None:
        pytest.skip("Linux flock required for quality gates")
    lock = tmp_path / "agent.lock"
    parent = subprocess.Popen(
        [
            "bash",
            "-c",
            'source "$1"; quality_lock_run "$2" bash -c '
            "'echo ready; read -r _'",
            "_",
            str(LOCK),
            str(lock),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert parent.stdout is not None
        readable, _, _ = select.select([parent.stdout], [], [], 3)
        assert readable, "lock holder did not signal ready within 3 seconds"
        assert parent.stdout.readline().strip() == "ready"
        contender = _bash(LOCK, f'quality_lock_run "{lock}" true')
        assert contender.returncode == 75
        assert "QG_LOCKED" in contender.stderr
        parent.communicate(input="\n", timeout=5)
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.communicate(timeout=5)
    recovered = _bash(LOCK, f'quality_lock_run "{lock}" true')
    assert recovered.returncode == 0, recovered.stderr
    assert lock.stat().st_mode & 0o777 == 0o600


def test_worker_sigkill_does_not_leave_lock_with_its_child(tmp_path: Path) -> None:
    """Background subprocesses must not inherit the lock after worker death."""
    if shutil.which("flock") is None:
        pytest.skip("Linux flock required for quality gates")
    lock = tmp_path / "agent.lock"
    script = (
        'source "$1"; quality_lock_run "$2" bash -c '
        "'sleep 2 >/dev/null 2>&1 & kill -KILL $$'"
    )
    stopped = subprocess.run(
        ["bash", "-c", script, "_", str(LOCK), str(lock)],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert stopped.returncode == 137
    acquired = _bash(LOCK, f'quality_lock_run "{lock}" true')
    assert acquired.returncode == 0, acquired.stderr


def test_legacy_lock_directory_is_not_deleted(tmp_path: Path) -> None:
    lock = tmp_path / "agent.lock"
    lock.mkdir()
    (lock / "pid").write_text("123\n", encoding="utf-8")
    result = _bash(LOCK, f'quality_lock_run "{lock}"')
    assert result.returncode == 75
    assert "QG_LOCK_LEGACY_DIR" in result.stderr
    assert (lock / "pid").exists()


def test_symlink_lock_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "safe"
    target.write_text("keep", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(target)
    result = _bash(LOCK, f'quality_lock_run "{link}"')
    assert result.returncode == 2
    assert "QG_LOCK_INVALID" in result.stderr
    assert target.read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize(
    ("code", "expected", "marker"),
    [
        ("exit 0", 0, ""),
        ("exit 42", 42, ""),
        ("sleep 2", 124, "QG_STEP_TIMEOUT"),
    ],
)
def test_bounded_gate_propagates_status(
    code: str, expected: int, marker: str
) -> None:
    if shutil.which("timeout") is None:
        pytest.skip("GNU timeout required")
    result = _bash(DEADLINE, f"quality_run_bounded 1 bash -c '{code}'")
    assert result.returncode == expected
    assert marker in result.stderr


@pytest.mark.parametrize("seconds", ["0", "3601", "bad", "0001"])
def test_invalid_budget_fails_closed(seconds: str) -> None:
    result = _bash(DEADLINE, f"quality_run_bounded {seconds} true")
    assert result.returncode == 2
    assert "QG_TIMEOUT_INVALID" in result.stderr



def test_precommit_deadline_stops_convergence_without_retry() -> None:
    gate = (ROOT / "scripts/agent-quality-gate.sh").read_text(encoding="utf-8")
    assert "QG_FIX_INTERRUPTED" in gate
    assert "if ((rc == 124 || rc == 137))" in gate
    assert "unset QUALITY_GATE_LOCK_WORKER" in gate


def test_lock_and_deadline_scripts_are_source_only() -> None:
    for path in (LOCK, DEADLINE):
        assert path.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")
        assert os.access(path, os.X_OK)
