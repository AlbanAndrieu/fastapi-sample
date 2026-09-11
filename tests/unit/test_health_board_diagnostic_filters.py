"""Contracts for health-board diagnostic filters and probe evidence."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"


def test_health_board_installs_diagnostic_filter_module() -> None:
    entrypoint = (ASSETS / "api-health.js").read_text(encoding="utf-8")
    stylesheet = (ASSETS / "api.css").read_text(encoding="utf-8")

    assert 'from "./api-service-diagnostics.js"' in entrypoint
    assert "installServiceDiagnostics();" in entrypoint
    assert "installServiceFilter();" not in entrypoint
    assert '@import url("./api-service-diagnostics.css");' in stylesheet


def test_diagnostic_filters_cover_status_exposure_and_probe_type() -> None:
    javascript = (ASSETS / "api-service-diagnostics.js").read_text(encoding="utf-8")

    for status in [
        "Operational",
        "At risk",
        "Degraded",
        "Down",
        "Unknown",
        "Issues only",
    ]:
        assert status in javascript

    for exposure in [
        "Policy compliant",
        "Policy warning",
        "Policy violation",
        "External services",
        "Internal-only services",
        "Cloudflare protected",
        "Direct / no tunnel",
    ]:
        assert exposure in javascript

    for probe in [
        "HTTP",
        "HTTPS / TLS",
        "TCP",
        "REST API",
        "WebSocket",
        "Cloudflare Tunnel",
        "Cloudflare Access",
        "Service Token",
        "Prometheus / metrics",
    ]:
        assert probe in javascript


def test_probe_evidence_uses_independent_colored_states() -> None:
    javascript = (ASSETS / "api-service-diagnostics.js").read_text(encoding="utf-8")
    stylesheet = (ASSETS / "api-service-diagnostics.css").read_text(encoding="utf-8")

    assert "cloudflare_service_token_access_passed" in javascript
    assert "cloudflare_tunnel_observed" in javascript
    assert "cloudflare_access_policy_count" in javascript
    assert "tls_trusted" in javascript
    assert 'probeBadge("tls"' in javascript
    assert 'probeBadge("cloudflare"' in javascript
    assert 'probeBadge("service-token"' in javascript
    assert 'probeBadge("metrics"' in javascript

    for tone in ["ok", "warn", "fail", "unknown", "neutral"]:
        assert f".service-probe--{tone}" in stylesheet


def test_collapse_control_toggles_to_expand_after_groups_are_closed() -> None:
    javascript = (ASSETS / "api-service-diagnostics.js").read_text(encoding="utf-8")

    assert 'button.textContent = anyOpen ? "Collapse" : "Expand";' in javascript
    assert 'button.setAttribute("aria-expanded", String(anyOpen));' in javascript
    assert "const shouldOpen = !groups.some((group) => group.open);" in javascript


def test_filters_are_reapplied_after_live_health_board_updates() -> None:
    javascript = (ASSETS / "api-service-diagnostics.js").read_text(encoding="utf-8")

    assert "new MutationObserver(scheduleRefresh)" in javascript
    assert 'observer.observe(board, { childList: true, subtree: true });' in javascript
    assert "latestSnapshot = await fetchHealthBoard()" in javascript
    assert "applyFilters();" in javascript
