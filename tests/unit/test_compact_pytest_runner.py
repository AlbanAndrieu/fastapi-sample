"""Offline contracts for the compact pytest runner (no uv or network required)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "run-pytest-compact.sh"


@pytest.mark.parametrize(
    ("exit_code", "output", "expected"),
    [
        (0, "1 passed in 0.01s\n", "1 passed"),
        (1, "FAILED tests/test_x.py::test_x - AssertionError\n", "FAILED tests/test_x.py"),
        (2, "ImportError: missing optional module\n", "ImportError: missing optional module"),
    ],
)
def test_runner_preserves_exit_code_and_compact_diagnostics(
    tmp_path: Path, exit_code: int, output: str, expected: str
) -> None:
    """Fake uv provides deterministic pytest output without downloading dependencies."""
    uv = tmp_path / "uv"
    uv.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$FAKE_PYTEST_OUTPUT\"\nexit \"$FAKE_PYTEST_EXIT\"\n",
        encoding="utf-8",
    )
    uv.chmod(0o755)
    log = tmp_path / "pytest.log"
    env = {
        **os.environ,
        "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}",
        "PYTEST_LOG_FILE": str(log),
        "FAKE_PYTEST_OUTPUT": output.rstrip("\n"),
        "FAKE_PYTEST_EXIT": str(exit_code),
    }
    result = subprocess.run(
        ["bash", str(RUNNER)], capture_output=True, text=True, env=env, check=False
    )
    assert result.returncode == exit_code
    assert expected in result.stdout + result.stderr
    assert log.exists() is (exit_code != 0)


def test_runner_rejects_non_numeric_limit_without_running_uv(tmp_path: Path) -> None:
    env = {**os.environ, "PYTEST_FAILURE_SUMMARY_LINES": "bad"}
    result = subprocess.run(
        ["bash", str(RUNNER)], capture_output=True, text=True, env=env, check=False
    )
    assert result.returncode == 2
    assert "non-negative integer" in result.stderr
