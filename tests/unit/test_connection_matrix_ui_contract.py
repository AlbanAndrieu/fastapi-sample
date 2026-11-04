"""Static contracts for server-derived infrastructure connection diagnostics."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_connections_use_existing_health_board_and_do_not_trigger_fanout() -> None:
    script = (ROOT / "nabla/api/assets/api-probe-fanout-dashboard.js").read_text()
    backend = (ROOT / "nabla/api/health_board.py").read_text()
    assert "connectionMatrixHtml" in script
    assert "probe-dashboard-connections" in script
    assert "lastConnectionMatrix" in script
    assert "connection_matrix" in script
    assert "connection_matrix" in backend
    assert "build_connection_matrix" in backend
    assert "fetch_external_connection_probes" in backend
    assert "fetch(" not in script


def test_external_checks_cannot_be_selected_by_query_or_untrusted_runtime() -> None:
    script = (ROOT / "nabla/api/external_connection_probes.py").read_text()
    assert 'homelab_runtime_detected()' in script
    assert '"https://fastapi-sample.fastapicloud.dev/api/ui/session"' in script
    assert '"https://cloudflare-dns.com/dns-query"' in script
    assert 'trust_env=False' in script
    assert 'follow_redirects=False' in script
    assert "_CACHE_TTL_SECONDS = 90.0" in script


def test_connection_matrix_warnings_do_not_age_into_false_green() -> None:
    dashboard = (ROOT / "nabla/api/assets/api-probe-fanout-dashboard.js").read_text()
    shared = (ROOT / "nabla/api/assets/api-homelab-health.js").read_text()
    assert "health_board_state" in shared
    assert "health_board_age_seconds" in shared
    assert 'meta?.state === "stale" || age > 180' in dashboard
    assert 'const state = stale' in dashboard
    assert 'historical / unverified' in dashboard


def test_connection_diagnostic_categories_have_visible_badges() -> None:
    script = (ROOT / "nabla/api/assets/api-probe-fanout-dashboard.js").read_text()
    assert "row?.diagnostic_category" in script
    assert "probe-error-badge" in script
    assert "escapeText(row.diagnostic_category)" in script
