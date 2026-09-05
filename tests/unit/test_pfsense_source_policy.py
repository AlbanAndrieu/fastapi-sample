"""Regression coverage for pfSense source-policy diagnostics."""

from nabla.api.health_board import _annotate_pfsense_source_policy


def test_fastapi_cloud_connect_timeout_gets_source_policy_hint() -> None:
    healthz = {
        "checks": {
            "pfsense": {
                "reachable": False,
                "error_kind": "connect_timeout",
                "failure_stage": "connect",
            }
        }
    }
    runtime = {
        "runtime_mode": "fastapi_cloud",
        "active_egress_ips": ["34.200.20.162"],
    }

    result = _annotate_pfsense_source_policy(healthz, runtime)

    source_policy = result["checks"]["pfsense"]["source_policy"]
    assert source_policy["state"] == "possible_source_policy_drift"
    assert source_policy["active_egress_ips"] == ["34.200.20.162"]
    assert source_policy["access_policy"] == "trusted_sources_only"
    assert source_policy["recommended_control_path"] == "out_of_band"


def test_non_cloud_timeout_is_not_over_attributed() -> None:
    healthz = {
        "checks": {
            "pfsense": {
                "reachable": False,
                "error_kind": "connect_timeout",
                "failure_stage": "connect",
            }
        }
    }

    result = _annotate_pfsense_source_policy(
        healthz,
        {"runtime_mode": "local", "active_egress_ips": ["192.0.2.10"]},
    )

    assert "source_policy" not in result["checks"]["pfsense"]
