"""Static contracts for live probe age, pending state, and tier help UI."""

from pathlib import Path


ASSETS = Path("nabla/api/assets")


def test_live_probe_ui_refreshes_age_without_network_each_second() -> None:
    javascript = (ASSETS / "api-probe-live.js").read_text(encoding="utf-8")

    assert "const AGE_TICK_MS = 1000;" in javascript
    assert "`${age}s ago`" in javascript
    assert 'badge.textContent = "probing…";' in javascript
    assert "probe_interval_seconds" in javascript
    assert "next_probe_in_seconds" not in javascript  # rendered from age/interval, not a stale countdown


def test_health_board_poll_is_cached_and_pauses_when_tab_is_hidden() -> None:
    controller = (ASSETS / "api-health-controller.js").read_text(encoding="utf-8")
    bootstrap = (ASSETS / "api-health.js").read_text(encoding="utf-8")

    assert "const HEALTH_BOARD_IDLE_POLL_MS = 10000;" in controller
    assert "const HEALTH_BOARD_REFRESHING_POLL_MS = 2000;" in controller
    assert "document.hidden" in controller
    assert "loadHealthBoards({ showPending: false })" in controller
    assert "snapshot?.refreshing === true" in controller
    assert "startProbeAgeTicker();" in bootstrap
    assert "installHealthBoardController();" in bootstrap


def test_health_tier_help_explains_required_and_optional_semantics() -> None:
    javascript = (ASSETS / "api-probe-live.js").read_text(encoding="utf-8")

    assert '"Required infra (albandrieu.com)"' in javascript
    assert '"Optional health check"' in javascript
    assert "availability tier" in javascript
    assert "non-blocking integration" in javascript
    assert "warning/unknown state rather than downtime" in javascript


def test_cloudflare_uncertainty_moves_to_card_and_disables_api_derived_controls() -> None:
    cloudflare = (ASSETS / "api-cloudflare-status.js").read_text(encoding="utf-8")
    diagnostics = (ASSETS / "api-service-diagnostics.js").read_text(encoding="utf-8")
    provider = (ASSETS / "api-service-probe-details.js").read_text(encoding="utf-8")
    controller = (ASSETS / "api-health-controller.js").read_text(encoding="utf-8")

    assert "retireLegacyTunnelStatusBlock" in cloudflare
    assert "Cloudflare verification unavailable" in cloudflare
    assert 'cls: "gray"' in cloudflare
    assert "state.disabled" in cloudflare
    assert "controlPlaneConfirmed" in cloudflare
    assert "cloudflareControlPlane" in diagnostics
    assert "data.probeDisabled" not in diagnostics  # dataset is assigned directly on the badge
    assert 'badge.dataset.probeDisabled = "true"' in diagnostics
    assert "Tunnel inventory cannot be verified" in diagnostics
    assert "Service Auth is an independent live edge proof" in diagnostics
    assert "Cloudflare diagnostics" in provider
    assert "Access & Service Auth" in provider
    assert "not a Cloudflare outage" in provider
    assert "snapshot?.healthz?.checks?.cloudflare" in controller
    assert "snapshot?.homelab?.cloudflare" in controller


def test_pfsense_security_controls_have_explicit_icons() -> None:
    javascript = (ASSETS / "api-security-control-icons.js").read_text(
        encoding="utf-8",
    )
    provider = (ASSETS / "api-service-probe-details.js").read_text(encoding="utf-8")
    flow = (ASSETS / "api-platform-flow-ui.js").read_text(encoding="utf-8")
    controller = (ASSETS / "api-health-controller.js").read_text(encoding="utf-8")

    assert '["Snort", "🛡️"]' in javascript
    assert '["pfBlockerNG", "🚫"]' in javascript
    assert '["Unbound", "🌐"]' in javascript
    assert 'return "🚫"' in provider
    assert 'return "🛡️"' in provider
    assert 'return "👥"' in provider
    assert "snort2c evidence unavailable" in provider
    assert "does not mean Snort or pfBlockerNG is stopped" in provider
    assert "truenas-stage-security-badge" in flow
    assert "MutationObserver" in javascript
    assert 'from "./api-security-control-icons.js"' in controller
    assert "installSecurityControlIcons();" in controller


def test_probe_detail_ticker_updates_only_dynamic_fields() -> None:
    javascript = (ASSETS / "api-service-probe-details.js").read_text(
        encoding="utf-8",
    )

    assert '"probe-state"' in javascript
    assert '"probe-age"' in javascript
    assert '"next-due"' in javascript
    assert 'const rendered = value == null || value === "" ? "—"' in javascript
    assert "window.setInterval(refreshDynamicTiming, TICK_MS);" in javascript
    assert "window.setInterval(scheduleRender, TICK_MS);" not in javascript


def test_live_probe_styles_are_loaded() -> None:
    styles = (ASSETS / "api.css").read_text(encoding="utf-8")

    assert '@import url("./api-probe-live.css");' in styles
    assert '@import url("./api-platform-diagnostics.css");' in styles
