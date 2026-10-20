"""UI contract: Prometheus/Gatus is reused, not fanned out from the browser."""

from pathlib import Path

ASSETS = Path(__file__).resolve().parents[2] / "nabla/api/assets"


def test_telemetry_badges_reuse_one_health_board_snapshot():
    module = (ASSETS / "api-service-telemetry.js").read_text()
    strips = (ASSETS / "api-service-probe-planes.js").read_text()
    drawer = (ASSETS / "api-service-probe-details.js").read_text()
    assert "export function serviceTelemetry(snapshot, row)" in module
    assert "synthetic_probes" in module and "exporter_jobs" in module
    assert "postgres_exporter" in module and "pfsense_exporter" in module
    assert "pg_up" in module
    assert "pfsense_memory_available_ratio" in module
    assert "no labeled per-service metrics" in module
    assert "fetch(" not in module
    assert "serviceTelemetry(snapshot, row)" in strips
    assert "serviceTelemetry(snapshot, row)" in drawer
    assert "Prometheus / Gatus / exporters" in drawer
    assert "decorateTelemetry(strip, snapshot, row)" in strips


def test_fanout_explains_unconfigured_and_rotating_targets_without_claiming_outages():
    script = (ASSETS / "api-probe-fanout-dashboard.js").read_text()
    for text in (
        "probe-dashboard-catalog",
        "catalog_unconfigured_service_count",
        "unsampled_current_window",
        "internal_disabled_eligible_slots",
        "outside the current rotating wave",
    ):
        assert text in script
