"""Validate agent quality log budgets without external dependencies."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "agent-quality-gate.sh"


@pytest.mark.parametrize(
    ("configured", "expected", "rc"),
    [
        (None, "20", 0),
        ("0", "0", 0),
        ("0009", "9", 0),
        ("0000000000000000", "0", 0),
        ("100", "80", 0),
        ("999999999999999999999999999999", "80", 0),
        ("broken", "", 2),
        ("-1", "", 2),
    ],
)
def test_quality_log_tail_normalization(
    configured: str | None, expected: str, rc: int
) -> None:
    """Exercise the exact Bash setup block from the tracked gate."""
    source = GATE.read_text(encoding="utf-8")
    block = source.split('LOG_TAIL="${QUALITY_LOG_TAIL:-20}"', maxsplit=1)[1]
    block = 'LOG_TAIL="${QUALITY_LOG_TAIL:-20}"' + block.split(
        'FIX_PASSES="${QUALITY_FIX_PASSES:-6}"', maxsplit=1
    )[0]
    env = os.environ.copy()
    env.pop("QUALITY_LOG_TAIL", None)
    if configured is not None:
        env["QUALITY_LOG_TAIL"] = configured
    result = subprocess.run(
        ["bash", "-c", 'set -euo pipefail\n' + block + '\nprintf "%s\\n" "$LOG_TAIL"'],
        env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == rc, result.stderr
    if rc == 0:
        assert result.stdout.strip() == expected
    else:
        assert "non-negative integer" in result.stderr


@pytest.mark.parametrize(
    ("configured", "expected", "rc"),
    [
        (None, "6", 0),
        ("0009", "9", 0),
        ("01", "1", 0),
        ("100", "20", 0),
        ("999999999999999999999999", "20", 0),
        ("0", "", 2),
        ("0000", "", 2),
        ("bad", "", 2),
    ],
)
def test_quality_fix_passes_are_decimal_and_bounded(
    configured: str | None, expected: str, rc: int
) -> None:
    """Convergence budget must not overflow or run an unbounded number of passes."""
    source = GATE.read_text(encoding="utf-8")
    marker = 'FIX_PASSES="${QUALITY_FIX_PASSES:-6}"'
    block = marker + source.split(marker, maxsplit=1)[1].split(
        "\nresolve_base_ref() {", maxsplit=1
    )[0]
    env = os.environ.copy()
    env.pop("QUALITY_FIX_PASSES", None)
    if configured is not None:
        env["QUALITY_FIX_PASSES"] = configured
    result = subprocess.run(
        ["bash", "-c", 'set -euo pipefail\n' + block + '\nprintf "%s\\n" "$FIX_PASSES"'],
        env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == rc, result.stderr
    if rc == 0:
        assert result.stdout.strip() == expected
    else:
        assert "positive integer" in result.stderr
