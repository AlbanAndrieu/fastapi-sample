"""Regression coverage for pfSense source-policy diagnostics."""

from nabla.api.health_board import (
    _annotate_pfsense_ingress_policy,
    _annotate_truenas_ingress_policy,
)


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

    result = _annotate_pfsense_ingress_policy(healthz, runtime)

    ingress_policy = result["checks"]["pfsense"]["ingress_policy"]
    assert ingress_policy["state"] == "possible_ingress_policy_block"
    assert ingress_policy["active_egress_ips"] == ["34.200.20.162"]
    assert ingress_policy["access_policy"] == "trusted_sources_only"
    assert ingress_policy["attribution_available"] is False
    assert ingress_policy["possible_causes"] == [
        "trusted_source_policy_drift",
        "pf_or_snort_filter",
    ]
    assert ingress_policy["recommended_control_path"] == "out_of_band"


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

    result = _annotate_pfsense_ingress_policy(
        healthz,
        {"runtime_mode": "local", "active_egress_ips": ["192.0.2.10"]},
    )

    assert "ingress_policy" not in result["checks"]["pfsense"]


def test_fastapi_cloud_truenas_connect_timeout_gets_ingress_hint() -> None:
    homelab = {
        "truenas": {
            "state": "warn",
            "appliance_state": "ok",
            "public_ingress_state": "fail",
            "public": {
                "reachable": False,
                "state": "fail",
                "error_kind": "connect_timeout",
                "failure_stage": "connect",
            },
        },
    }
    runtime = {
        "runtime_mode": "fastapi_cloud",
        "active_egress_ips": ["34.200.20.162"],
    }

    result = _annotate_truenas_ingress_policy(homelab, runtime)

    truenas = result["truenas"]
    assert truenas["appliance_state"] == "ok"
    assert truenas["public_ingress_state"] == "fail"
    assert truenas["ingress_policy"]["state"] == "possible_ingress_policy_block"
    assert truenas["ingress_policy"]["active_egress_ips"] == ["34.200.20.162"]
    assert truenas["ingress_policy"]["first_failing_layer"] == "tcp_connect"
    assert truenas["ingress_policy"]["destination_port"] == 7000
    assert truenas["ingress_policy"]["attribution_available"] is False


def test_truenas_http_failure_is_not_misclassified_as_ingress_policy() -> None:
    homelab = {
        "truenas": {
            "public": {
                "reachable": False,
                "state": "fail",
                "error_kind": "http_502",
                "failure_stage": "http_response",
            },
        },
    }

    result = _annotate_truenas_ingress_policy(
        homelab,
        {"runtime_mode": "fastapi_cloud", "active_egress_ips": ["34.200.20.162"]},
    )

    assert "ingress_policy" not in result["truenas"]
