"""Contracts for health-board diagnostic filters and probe evidence."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"


def test_health_board_installs_diagnostic_filter_module() -> None:
    entrypoint = (ASSETS / "api-health.js").read_text(encoding="utf-8")
    diagnostics = (ASSETS / "api-service-diagnostics.js").read_text(encoding="utf-8")
    stylesheet = (ASSETS / "api.css").read_text(encoding="utf-8")

    assert 'from "./api-service-diagnostics.js"' in entrypoint
    assert "installServiceDiagnostics();" in entrypoint
    assert 'from "./api-service-filter.js"' in diagnostics
    assert "installServiceFilter();" in diagnostics
    assert '@import url("./api-service-diagnostics.css");' in stylesheet


def test_global_filters_cover_site_aligned_environment_group_and_status() -> None:
    javascript = (ASSETS / "api-service-filter.js").read_text(encoding="utf-8")

    for status in [
        "Operational",
        "At risk",
        "Degraded",
        "Down",
        "Unknown",
        "Issues only",
    ]:
        assert status in javascript

    for environment in [
        "Production + Staging (exclude Dev)",
        "Production",
        "Staging",
        "Dev",
        "Default production (review metadata)",
    ]:
        assert environment in javascript

    for group in [
        "Services & experiments",
        "Critical core platform",
        "Security controls",
        "Shared platform & data",
        "Observability & support",
        "External / optional",
    ]:
        assert group in javascript

    assert 'row.dataset.environmentSource === "default"' in javascript
    assert 'environment !== "dev"' in javascript
    assert "row.dataset.presentationGroup === filters.group" in javascript


def test_diagnostic_filters_cover_exposure_and_probe_type() -> None:
    javascript = (ASSETS / "api-service-filter.js").read_text(encoding="utf-8")

    for exposure in [
        "Policy compliant",
        "Policy warning",
        "Policy violation",
        "No exposure evidence",
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
    assert "cloudflare_service_token_http_status" in javascript
    assert "cloudflare_tunnel_observed" in javascript
    assert "cloudflare_access_policy_count" in javascript
    assert "cloudflare_default_deny" in javascript
    assert "tls_trusted" in javascript
    for probe_kind in ["tls", "cloudflare", "service-token", "metrics"]:
        assert re.search(rf'probeBadge\(\s*"{re.escape(probe_kind)}"', javascript)

    for tone in ["ok", "warn", "fail", "unknown", "neutral"]:
        assert f".service-probe--{tone}" in stylesheet


def test_probe_tooltips_keep_diagnostic_provenance() -> None:
    javascript = (ASSETS / "api-service-diagnostics.js").read_text(encoding="utf-8")

    for evidence in [
        "elapsed_ms",
        "cache_age_seconds",
        "cache_layer",
        "stale",
        "refreshing",
        "vantage_point",
        "failure_stage",
        "error_kind",
        "credential_mode",
        "last_success_at",
    ]:
        assert evidence in javascript
    assert "evidenceMetadata(evidence)" in javascript


def test_collapse_control_toggles_to_expand_after_groups_are_closed() -> None:
    javascript = (ASSETS / "api-service-filter.js").read_text(encoding="utf-8")

    assert 'button.textContent = anyOpen ? "Collapse" : "Expand";' in javascript
    assert 'button.setAttribute("aria-expanded", String(anyOpen));' in javascript
    assert "const shouldOpen = !groups.some((group) => group.open);" in javascript


def test_filters_are_reapplied_after_live_health_board_updates() -> None:
    javascript = (ASSETS / "api-service-diagnostics.js").read_text(encoding="utf-8")

    assert "new MutationObserver(scheduleRefresh)" in javascript
    assert "observer.observe(board, { childList: true, subtree: true });" in javascript
    assert "latestSnapshot = await fetchHealthBoard()" in javascript
    assert "refreshServiceFilter();" in javascript


def test_issues_button_tracks_status_filter_and_clear_state() -> None:
    javascript = (ASSETS / "api-service-filter.js").read_text(encoding="utf-8")

    assert "function syncIssuesButton()" in javascript
    assert 'button.textContent = active ? "All" : "Issues";' in javascript
    assert 'button.setAttribute("aria-pressed", String(active));' in javascript
    assert "syncIssuesButton();" in javascript
