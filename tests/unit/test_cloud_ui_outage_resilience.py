"""Cloud landing should remain usable while LAN diagnostics are degraded."""

from pathlib import Path

ASSETS = Path(__file__).resolve().parents[2] / "nabla/api/assets"


def read(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def test_session_bootstrap_is_bounded_and_fails_closed_to_public():
    session = read("api-owner-session.js")
    bootstrap = read("api-health.js")
    assert "withRequestDeadline(async (signal)" in session
    assert "SESSION_DEADLINE_MS = 4500" in session
    assert 'fetch("/api/ui/session"' in session
    assert "authenticated: false" in session
    assert "readOnly: false" in session
    assert "await installPublicServiceOverview();" in bootstrap


def test_public_catalog_has_own_bounded_request_and_useful_error_state():
    public = read("api-public-services.js")
    assert "withRequestDeadline(async (signal)" in public
    assert 'fetch("/api/ui/services"' in public
    assert "}, 6500)" in public
    assert "Service inventory unavailable" in public
    assert "rows.length > 0" in public
    assert "all statuses UNKNOWN" in public


def test_health_board_cannot_keep_browser_pending_for_one_minute():
    board = read("api-health-board.js")
    assert "fetchUntilReady(attemptsRemaining = 1)" in board
    assert "withRequestDeadline(async (signal)" in board
    assert "}, 6000)" in board
    assert "Math.min(2" in board
    assert "health snapshot refresh timed out" in board


def test_readonly_public_directory_stays_visible_until_detailed_snapshot_arrives():
    bootstrap = read("api-health.js")
    fallback = read("api-health-visibility.js")
    assert "if (!authenticated) await visibility.installReadOnlyPublicFallback();" in bootstrap
    assert 'document.addEventListener("health-board-refreshed"' in fallback
    assert "ownerAuthenticated: false" in fallback
    assert "detailedReady = true" in fallback
    assert "fallback.hidden = true" in fallback


def test_optional_lan_data_is_lazy_and_tickers_do_not_rewrite_all_rows_each_second():
    controller = read("api-health-controller.js")
    ticker = read("api-probe-live.js")
    http = read("api-http-probe-status.js")
    assert "loadHealthBoards({ includeTechnical: technicalDetailsOpen() })" in controller
    assert "HEALTH_BOARD_ERROR_BACKOFF_MS = 60000" in controller
    assert "const AGE_TICK_MS = 10000;" in ticker
    assert "lastSnapshot && !document.hidden" in ticker
    assert "window.setInterval(schedule, 1000)" not in http


def test_timeout_covers_transport_and_json_and_aborts():
    source = read("api-request-deadline.js")
    assert "Promise.race" in source
    assert "controller.abort()" in source
    assert "window.clearTimeout(timeout)" in source
    assert "task(controller.signal)" in source
