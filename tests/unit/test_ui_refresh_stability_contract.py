"""Static contracts for stable operator refresh and collapsed technical panels."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_service_board_precedes_technical_drilldowns_and_runtime_is_collapsed() -> None:
    ui = (ROOT / "nabla/api/ui.py").read_text(encoding="utf-8")
    assert ui.index('class="health-board"') < ui.index('class="truenas-platform"')
    assert ui.index('class="truenas-platform"') < ui.index('class="runtime-topology"')
    runtime_line = next(line for line in ui.splitlines() if 'id="runtime-topology"' in line)
    assert " open " not in runtime_line


def test_automatic_refresh_does_not_reload_collapsed_technical_drilldowns() -> None:
    javascript = (ROOT / "nabla/api/assets/api-health.js").read_text(encoding="utf-8")
    assert "includeTechnical = false" in javascript
    assert "loadHealthBoards({ includeTechnical: true })" in javascript
    assert "technicalDetailsOpen()" in javascript
    assert 'id="runtime-topology"' in javascript
    assert 'id="truenas-probe-dashboard"' in javascript


def test_fanout_and_advisory_pfsense_telemetry_are_collapsible() -> None:
    fanout = (ROOT / "nabla/api/assets/api-probe-fanout-dashboard.js").read_text(encoding="utf-8")
    truenas = (ROOT / "nabla/api/assets/api-truenas.js").read_text(encoding="utf-8")
    assert 'document.createElement("details")' in fanout
    assert "if (!root.open)" in fanout
    assert "Refresh details" in fanout
    assert 'container = document.createElement("details")' in truenas
    assert "container.open = wasOpen" in truenas
    assert "container.open = true" in truenas


def test_service_and_exposure_lists_have_stable_render_guards() -> None:
    health = (ROOT / "nabla/api/assets/api-health-core.js").read_text(encoding="utf-8")
    sickz = (ROOT / "nabla/api/assets/api-sickz.js").read_text(encoding="utf-8")
    assert "lastHealthRowsSignature" in health
    assert "signature === lastHealthRowsSignature" in health
    assert "lastSickzRowsSignature" in sickz
    assert "signature === lastSickzRowsSignature" in sickz
