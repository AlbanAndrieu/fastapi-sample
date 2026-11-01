"""Behavioral tests for the bounded, fail-closed CI pytest runner."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/ci/run-pytest-bounded.sh"


def execute(tmp_path: Path, mode: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(RUNNER), mode, *args],
        cwd=tmp_path,
        env={**os.environ, "TMPDIR": str(tmp_path), **(env or {})},
        capture_output=True,
        text=True,
        check=False,
        timeout=8,
    )


def fake_timeout(tmp_path: Path, code: int) -> tuple[Path, Path]:
    """Only mock the timeout binary for instant exit-code tests."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    args_log = tmp_path / "timeout-args.txt"
    command = bindir / "timeout"
    command.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$MOCK_TIMEOUT_ARGS\"\n"
        f"echo 'synthetic diagnostics' >&2\nexit {code}\n",
        encoding="utf-8",
    )
    command.chmod(0o755)
    return bindir, args_log


def test_full_success_preserves_summary_timing_and_log(tmp_path: Path) -> None:
    output = tmp_path / "output.txt"
    summary = tmp_path / "summary.md"
    result = execute(
        tmp_path,
        "full",
        sys.executable,
        "-c",
        "print('2 passed')",
        env={"GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY": str(summary)},
    )
    assert result.returncode == 0, result.stderr
    assert "2 passed" in result.stdout
    assert (tmp_path / "pytest.log").read_text(encoding="utf-8").strip() == "2 passed"
    assert "seconds=" in output.read_text(encoding="utf-8")
    assert "### pytest" in summary.read_text(encoding="utf-8")


def test_isolated_success_cleans_temporary_logs(tmp_path: Path) -> None:
    result = execute(tmp_path, "isolated", sys.executable, "-c", "print('contracts passed')")
    assert result.returncode == 0, result.stderr
    assert "isolated pytest contracts passed" in result.stdout
    assert not list(tmp_path.glob("ci-pytest.*"))
    assert not (tmp_path / "pytest.log").exists()


def test_pytest_failure_does_not_get_suppressed(tmp_path: Path) -> None:
    result = execute(tmp_path, "full", sys.executable, "-c", "print('failing test'); raise SystemExit(3)")
    assert result.returncode == 3
    assert "PYTEST_FAILED" in result.stderr
    assert "failing test" in result.stderr
    assert "last 180 lines" in result.stderr


@pytest.mark.parametrize(
    ("exit_code", "marker"),
    [(124, "PYTEST_TIMEOUT"), (137, "PYTEST_KILLED")],
)
def test_expected_fail_closed_diagnostics(tmp_path: Path, exit_code: int, marker: str) -> None:
    bindir, args_log = fake_timeout(tmp_path, exit_code)
    result = execute(
        tmp_path,
        "isolated",
        sys.executable,
        "-c",
        "print('not executed')",
        env={
            "PATH": str(bindir) + os.pathsep + os.environ.get("PATH", ""),
            "MOCK_TIMEOUT_ARGS": str(args_log),
        },
    )
    assert result.returncode == exit_code
    assert marker in result.stderr
    assert "synthetic diagnostics" in result.stderr
    arguments = args_log.read_text(encoding="utf-8").splitlines()
    assert arguments[:3] == ["--signal=TERM", "--kill-after=30s", "6m"]
    assert arguments[3] == sys.executable
    assert not list(tmp_path.glob("ci-pytest.*"))


def test_invalid_mode_and_missing_command_are_rejected(tmp_path: Path) -> None:
    for mode, args in [("typo", [sys.executable]), ("full", [])]:
        result = execute(tmp_path, mode, *args)
        assert result.returncode == 2
        assert "usage:" in result.stderr


def test_runner_is_executable(tmp_path: Path) -> None:
    assert RUNNER.stat().st_mode & 0o100
