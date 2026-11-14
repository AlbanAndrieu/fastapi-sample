"""Blue "expected by design" state: run its hermetic JS tests from pytest."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla/api/assets"


def test_expected_state_logic_is_hermetic() -> None:
    if shutil.which("node") is None:
        pytest.skip("Node.js unavailable")
    process = subprocess.run(
        ["node", "--test", str(ROOT / "tests/js/expected-by-design.test.mjs")],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert process.returncode == 0, process.stdout + process.stderr


def test_legend_and_styles_declare_blue_expected_state() -> None:
    legend = (ASSETS / "api-health-ui-polish.js").read_text(encoding="utf-8")
    assert '"health-legend--blue"' in legend
    styles = (ASSETS / "api-service-experience.css").read_text(encoding="utf-8")
    assert ".service-probe-path-step--expected" in styles
    assert ".truenas-stage--expected" in styles
    # Status words keep one width so "Pass"/"Warning" never resize a card.
    assert ".service-probe-path-step-state" in styles
    assert "min-width: 11ch" in styles


def test_drawer_evidence_has_a_single_writer() -> None:
    grid = (ASSETS / "api-health-ui-probe-grid.js").read_text(encoding="utf-8")
    assert 'getElementById("service-detail-evidence")' not in grid
    drawer = (ASSETS / "api-service-detail-drawer.js").read_text(encoding="utf-8")
    assert "host.dataset.structure === structure" in drawer


def read(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def test_each_card_badge_has_one_status_writer() -> None:
    # Two writers with different evidence flipped these badges every refresh.
    planes = read("api-service-probe-planes.js")
    assert "toneClass(http" not in planes
    assert 'tunnel.dataset.statusOwner !== "cloudflare-probe"' in planes
    assert 'badge.dataset.statusOwner = "cloudflare-probe"' in read("api-cloudflare-probe.js")
    http = read("api-http-probe-status.js")
    assert "latestSnapshot?.homelab?.public_probe_results" in http
    assert 'addEventListener("service-filter-changed", schedule)' in http
    diagnostics = read("api-service-diagnostics.js")
    assert 'for (const kind of ["http", "cloudflare"])' in diagnostics


def test_refresh_updates_nodes_in_place() -> None:
    grid = read("api-health-ui-probe-grid.js")
    assert "refreshDetails(grid.children, sources" in grid
    assert "probeDetail(probe, label)," not in grid
    planes = read("api-service-probe-planes.js")
    assert "strip.replaceChildren();" not in planes
    assert "node.dataset.planeKey === key" in planes
    operator = read("api-service-operator-diagnostics.js")
    assert "function replaceIfChanged(current, next, parent)" in operator
    assert "current?.isEqualNode(badge)" in operator
    followup = read("api-health-ui-final-followup.js")
    assert 'kind !== "issues"' in followup
    assert "#service-probe-legend[data-health-legend-complete" in read("api-probe-live.js")
