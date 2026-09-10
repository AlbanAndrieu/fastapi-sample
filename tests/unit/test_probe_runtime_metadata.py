"""Probe-runtime metadata must describe evidence warm-up without extra I/O."""

from nabla.api.health_routes import _probe_runtime_metadata


def test_probe_runtime_metadata_reports_progress_and_priority_aware_cadence() -> None:
    payload = {
        "probe_summary": {
            "public": {
                "enabled": True,
                "eligible": 22,
                "evidence": {"known": 21},
            },
            "internal": {
                "enabled": True,
                "eligible": 71,
                "evidence": {"known": 24},
            },
        },
        "public_probe_results": [
            {"probe_interval_seconds": 30.0},
            {"probe_interval_seconds": 120.0},
        ],
        "internal_services": [
            {"probe_interval_seconds": 30.0},
            {"probe_interval_seconds": 270.0},
        ],
    }

    metadata = _probe_runtime_metadata(payload)

    assert metadata["state"] == "warming"
    assert metadata["eligible_probe_slots"] == 93
    assert metadata["known_probe_slots"] == 45
    assert metadata["coverage_percent"] == 48.4
    assert metadata["estimated_full_cycle_seconds"] == 270.0
    assert metadata["uptime_seconds"] >= 0
    assert metadata["started_at"].endswith("Z")


def test_probe_runtime_metadata_excludes_disabled_scope_and_reports_ready() -> None:
    payload = {
        "probe_summary": {
            "public": {
                "enabled": True,
                "eligible": 2,
                "evidence": {"known": 2},
            },
            "internal": {
                "enabled": False,
                "eligible": 71,
                "evidence": {"known": 12},
            },
        },
        "public_probe_results": [{"probe_interval_seconds": 30.0}],
        "internal_services": [],
    }

    metadata = _probe_runtime_metadata(payload)

    assert metadata["state"] == "ready"
    assert metadata["eligible_probe_slots"] == 2
    assert metadata["known_probe_slots"] == 2
    assert metadata["coverage_percent"] == 100.0
    assert metadata["estimated_full_cycle_seconds"] == 30.0
