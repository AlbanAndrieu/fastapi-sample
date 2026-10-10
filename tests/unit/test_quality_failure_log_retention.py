"""Hermetic contracts for opt-in quality failure log retention."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "agent-quality-gate.sh"


@pytest.mark.parametrize("report", [False, True])
@pytest.mark.parametrize("retain", [False, True])
def test_compact_failure_preserves_exit_and_opt_in_log(
    tmp_path: Path, report: bool, retain: bool
) -> None:
    """Execute the real function text, without invoking any scanner or CI."""
    source = GATE.read_text(encoding="utf-8")
    functions = source.split("retain_failure_log() {", maxsplit=1)[1]
    functions = "retain_failure_log() {" + functions.split(
        "\nprint_precommit_failure() {", maxsplit=1
    )[0]
    selected = "run_compact_report" if report else "run_compact"
    env = os.environ.copy()
    env.pop("QUALITY_FAILURE_LOG_DIR", None)
    directory = tmp_path / "failure logs"
    if retain:
        env["QUALITY_FAILURE_LOG_DIR"] = str(directory)
    script = (
        "set -euo pipefail\n"
        "LOG_TAIL=1\n"
        + functions
        + f'\n{selected} sample bash -c \'printf "first\\nsecond\\n"; exit 17\'\n'
    )
    result = subprocess.run(
        ["bash", "-c", script], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 17
    assert "second" in result.stderr
    assert "first" not in result.stderr
    if retain:
        logs = list(directory.glob("quality-failure.*.log"))
        assert len(logs) == 1
        assert logs[0].read_text(encoding="utf-8") == "first\nsecond\n"
        assert logs[0].stat().st_mode & 0o077 == 0
    else:
        assert not directory.exists()


def test_compact_success_does_not_retain_log(tmp_path: Path) -> None:
    source = GATE.read_text(encoding="utf-8")
    functions = "retain_failure_log() {" + source.split(
        "retain_failure_log() {", maxsplit=1
    )[1].split("\nprint_precommit_failure() {", maxsplit=1)[0]
    directory = tmp_path / "quality logs"
    env = {**os.environ, "QUALITY_FAILURE_LOG_DIR": str(directory)}
    result = subprocess.run(
        ["bash", "-c", "set -euo pipefail\nLOG_TAIL=1\n" + functions
         + '\nrun_compact success bash -c \'echo ok\'\n'],
        env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert not directory.exists()
