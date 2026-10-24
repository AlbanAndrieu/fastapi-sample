"""Read-only UI contracts for service cards, protocol filters and probe flows."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"


def asset(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def test_diagnostic_stylesheet_is_loaded_after_legacy_overrides() -> None:
    styles = asset("api.css")
    assert styles.index("api-service-experience.css") > styles.index(
        "api-health-ui-final-followup.css"
    )
    presentation = asset("api-service-experience.css")
    assert ".service-protocol-shortcuts" in presentation
    assert ".service-probe-path-phase" in presentation
    assert "grid-template-columns: repeat(auto-fit" in presentation
    assert "@media (max-width: 720px)" in presentation
    assert ":focus-visible" in presentation


def test_protocol_grid_reports_unsampled_and_disabled_checks() -> None:
    script = asset("api-health-ui-probe-grid.js")
    positions = [script.index(f'["{name}",') for name in ("dns", "tcp", "tls", "http")]
    assert positions == sorted(positions)
    assert '["Network", ["dns", "tcp", "tls"]]' in script
    assert '["Edge", ["http", "cloudflare", "access", "service-token"]]' in script
    assert '"Not sampled"' in script
    assert '"Disabled"' in script
    assert 'grid.setAttribute("role", "list")' in script
    assert 'chip.setAttribute("aria-label"' in script


def test_filter_shortcuts_use_existing_select_and_url_state() -> None:
    script = asset("api-service-filter.js")
    for protocol in ("dns", "tcp", "tls", "http", "api", "websocket"):
        assert f'["{protocol}",' in script
    assert 'button.dataset.protocolShortcut = value' in script
    assert 'control.dispatchEvent(new Event("change"' in script
    assert '"aria-pressed"' in script
    assert 'probe.dataset.probePlaceholder !== "true"' in script
    global_filter = asset("api-global-service-filter.js")
    assert 'panel.dataset.probeKinds = [...protocols].join(" ")' in global_filter
    assert 'panel.dataset.probeKinds = "http tls api websocket"' not in global_filter


def test_flow_distinguishes_failure_from_unconfirmed_evidence() -> None:
    script = asset("api-truenas.js")
    assert 'pfsense_wan_ingress: "WAN route"' in script
    assert 'const failed = left?.state === "fail" || right?.state === "fail"' in script
    assert 'uncertain ? "unknown" : "ok"' in script
    assert '"truenas-stage-protocol"' in script
    assert '"truenas-stage-outcome"' in script
    html = (ROOT / "nabla" / "api" / "ui.py").read_text(encoding="utf-8")
    assert 'id="truenas-pipeline" role="group"' in html
    assert "No result is inferred from another step." in html
