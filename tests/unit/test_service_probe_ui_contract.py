from pathlib import Path


ASSETS = Path(__file__).resolve().parents[2] / "nabla" / "api" / "assets"


def test_service_groups_decorate_probe_evidence() -> None:
    javascript = (ASSETS / "api-service-groups.js").read_text(encoding="utf-8")
    assert 'from "./api-service-probes.js"' in javascript
    assert "decorateServiceProbeEvidence(" in javascript
    assert "platformMetrics" in javascript


def test_probe_ui_distinguishes_runtime_and_probe_channels() -> None:
    javascript = (ASSETS / "api-service-probes.js").read_text(encoding="utf-8")
    for label in (
        "TrueNAS",
        "pfSense",
        "Prom",
        "TCP",
        "Public HTTPS",
        "CF token",
        "TLS",
    ):
        assert label in javascript
    assert "runtime_containers" in javascript
    assert "cloudflare_service_token_error_kind" in javascript
    assert "direct_probe_error_kind" in javascript
    assert "internal_probe_error_kind" in javascript


def test_probe_styles_are_loaded() -> None:
    stylesheet = (ASSETS / "api.css").read_text(encoding="utf-8")
    styles = (ASSETS / "api-service-probes.css").read_text(encoding="utf-8")
    assert '@import url("./api-service-probes.css");' in stylesheet
    assert ".service-runtime-badge--ok" in styles
    assert ".service-runtime-badge--starting" in styles
    assert ".service-probe-chip--ok" in styles
    assert ".service-probe-chip--error" in styles
    assert ".service-probe-chip--stale" in styles


def test_service_grouping_wires_probe_evidence_decorator() -> None:
    javascript = Path("nabla/api/assets/api-service-groups.js").read_text()
    assert "decorateServiceProbeEvidence" in javascript
    assert "platformMetrics" in javascript
