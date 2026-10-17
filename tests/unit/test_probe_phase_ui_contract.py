"""Read-only UI contracts for phase-attributed homelab fan-out diagnostics."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla/api/assets"
DASHBOARD = ASSETS / "api-probe-fanout-dashboard.js"
HELPER = ASSETS / "api-probe-phase-timing.js"
JS_TEST = ROOT / "tests/js/probe-phase-timing.mjs"


def test_probe_dashboard_shows_completed_phase_samples_without_extra_fetches() -> None:
    dashboard = DASHBOARD.read_text(encoding="utf-8")
    helper = HELPER.read_text(encoding="utf-8")
    assert 'from "./api-probe-phase-timing.js"' in dashboard
    assert "phaseSummaryText(" in dashboard
    assert "phaseDetailText(row?.probe_timing)" in dashboard
    assert "scope.phaseTiming" in dashboard
    assert "completed_samples" in helper
    assert "deadline (phase unknown)" in helper
    assert "fetch(" not in helper


def test_phase_evidence_is_observed_only_and_hermetic() -> None:
    if shutil.which("node") is None:
        pytest.skip("Node.js unavailable")

    process = subprocess.run(
        ["node", str(JS_TEST), str(HELPER)],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert process.returncode == 0, process.stdout + process.stderr
