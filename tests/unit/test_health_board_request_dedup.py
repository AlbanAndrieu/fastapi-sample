"""Regression guards for health-board network request fan-out."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"


def test_health_board_reuses_one_aggregate_request_per_refresh() -> None:
    shared = (ASSETS / "api-homelab-health.js").read_text(encoding="utf-8")
    board = (ASSETS / "api-health-board.js").read_text(encoding="utf-8")
    bootstrap = (ASSETS / "api-health.js").read_text(encoding="utf-8")
    controller = (ASSETS / "api-health-controller.js").read_text(encoding="utf-8")
    health = (ASSETS / "api-health-core.js").read_text(encoding="utf-8")
    truenas = (ASSETS / "api-truenas.js").read_text(encoding="utf-8")

    assert '/api/health-board${force ? "?refresh=true" : ""}' in board
    assert "let healthBoardRequest = null" in board
    assert "resetHealthBoardRequest({ forceRefresh });" in controller
    assert "loadTrueNas();" in controller
    assert "finally(() => loadTrueNas())" not in controller
    assert "installHealthBoardController();" in bootstrap
    assert 'from "./api-health-board.js"' in health
    assert 'from "./api-homelab-health.js"' in truenas
    assert 'from "./api-health-board.js"' in shared
    assert 'fetch("/healthz"' not in health
    assert 'fetch("/sickz"' not in controller
    assert 'fetch("/api/homelab/health"' not in health
    assert 'fetch("/api/homelab/health"' not in truenas


def test_truenas_uses_public_health_board_as_primary_render_path() -> None:
    shared = (ASSETS / "api-homelab-health.js").read_text(encoding="utf-8")
    truenas = (ASSETS / "api-truenas.js").read_text(encoding="utf-8")

    assert 'fetch("/api/homelab/probes"' in shared
    assert "publishAggregateProbeSnapshot" in shared
    assert 'probe_snapshot_source: "health-board"' in shared
    assert "fetchHomelabProbeMatrix" not in truenas
    assert "const aggregate = await fetchHomelabHealth()" in truenas
    assert 'cache: "no-store"' in shared


def test_protected_or_missing_raw_probe_matrix_does_not_replace_public_aggregate_health(
) -> None:
    shared = (ASSETS / "api-homelab-health.js").read_text(encoding="utf-8")
    truenas = (ASSETS / "api-truenas.js").read_text(encoding="utf-8")

    assert '"diagnostics_auth_required"' in shared
    assert '"probe_matrix_unavailable"' in shared
    assert "lastRenderedSnapshot" in truenas
    assert "health snapshot unavailable" in truenas
    assert (
        "Raw probe authentication does not mark TrueNAS or the probe fan-out down."
        in truenas
    )
