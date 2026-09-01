"""Regression guards for health-board network request fan-out."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"


def test_health_board_reuses_one_homelab_request_per_refresh() -> None:
    shared = (ASSETS / "api-homelab-health.js").read_text(encoding="utf-8")
    bootstrap = (ASSETS / "api-health.js").read_text(encoding="utf-8")
    health = (ASSETS / "api-health-core.js").read_text(encoding="utf-8")
    truenas = (ASSETS / "api-truenas.js").read_text(encoding="utf-8")

    assert 'fetch("/api/homelab/health"' in shared
    assert "let homelabHealthRequest = null" in shared
    assert "resetHomelabHealthRequest();" in bootstrap
    assert 'from "./api-homelab-health.js"' in health
    assert 'from "./api-homelab-health.js"' in truenas
    assert 'fetch("/api/homelab/health"' not in health
    assert 'fetch("/api/homelab/health"' not in truenas
