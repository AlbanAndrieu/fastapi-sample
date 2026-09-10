"""Static contracts for live probe age, pending state, and tier help UI."""

from pathlib import Path


ASSETS = Path("nabla/api/assets")


def test_live_probe_ui_refreshes_age_without_network_each_second() -> None:
    javascript = (ASSETS / "api-probe-live.js").read_text(encoding="utf-8")

    assert "const AGE_TICK_MS = 1000;" in javascript
    assert '`${age}s ago`' in javascript
    assert 'badge.textContent = "probing…";' in javascript
    assert "probe_interval_seconds" in javascript
    assert "next_probe_in_seconds" not in javascript  # rendered from age/interval, not a stale countdown


def test_health_board_poll_is_cached_and_pauses_when_tab_is_hidden() -> None:
    javascript = (ASSETS / "api-health.js").read_text(encoding="utf-8")

    assert "const HEALTH_BOARD_POLL_MS = 5000;" in javascript
    assert "document.hidden" in javascript
    assert "loadHealthBoards({ showPending: false })" in javascript
    assert "startProbeAgeTicker();" in javascript


def test_health_tier_help_explains_required_and_optional_semantics() -> None:
    javascript = (ASSETS / "api-probe-live.js").read_text(encoding="utf-8")

    assert '"Required infra (albandrieu.com)"' in javascript
    assert '"Optional health check"' in javascript
    assert "availability tier" in javascript
    assert "non-blocking integration" in javascript
    assert "warning/unknown state rather than downtime" in javascript


def test_live_probe_styles_are_loaded() -> None:
    styles = (ASSETS / "api.css").read_text(encoding="utf-8")

    assert '@import url("./api-probe-live.css");' in styles
