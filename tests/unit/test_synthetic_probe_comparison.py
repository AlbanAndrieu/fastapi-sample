"""Tests for direct-vs-Gatus shadow probe reconciliation."""

from nabla.api.synthetic_probe_comparison import compare_synthetic_probe_evidence


def _platform(services: dict) -> dict:
    return {
        "synthetic_probes": {
            "source": "gatus_via_prometheus",
            "shadow_only": True,
            "services": services,
        }
    }


def test_shadow_comparison_matches_equivalent_http_and_tcp_probes() -> None:
    homelab = {
        "public_probe_results": [
            {"id": "fastapi-sample", "state": "ok"},
            {"id": "vaultwarden", "state": "fail"},
        ],
        "internal_services": [
            {"id": "fastapi-sample", "state": "ok"},
        ],
    }
    platform = _platform(
        {
            "fastapi-sample": {
                "HTTP": {"success": 1.0},
                "TCP": {"success": 1.0},
            },
            "vaultwarden": {"HTTP": {"success": 0.0}},
        }
    )

    result = compare_synthetic_probe_evidence(homelab, platform)

    assert result["comparable"] == 3
    assert result["matched"] == 3
    assert result["mismatched"] == 0
    assert result["missing_gatus"] == 0
    assert result["mismatches"] == []


def test_shadow_comparison_reports_mismatch_without_affecting_verdicts() -> None:
    homelab = {
        "public_probe_results": [
            {"id": "garage", "state": "ok"},
            {"id": "ignored-warning", "state": "warn"},
        ],
        "internal_services": [
            {"id": "nexus", "state": "fail"},
            {"id": "missing", "state": "ok"},
        ],
    }
    platform = _platform(
        {
            "garage": {"HTTP": {"success": 0.0}},
            "ignored-warning": {"HTTP": {"success": 0.0}},
            "nexus": {"TCP": {"success": 0.0}},
        }
    )

    result = compare_synthetic_probe_evidence(homelab, platform)

    assert result["shadow_only"] is True
    assert result["comparable"] == 2
    assert result["matched"] == 1
    assert result["mismatched"] == 1
    assert result["missing_gatus"] == 1
    assert result["mismatches"] == [
        {
            "id": "garage",
            "scope": "public",
            "direct_state": "ok",
            "gatus_type": "HTTP",
            "gatus_success": 0.0,
        }
    ]


def test_shadow_comparison_is_unavailable_without_synthetic_services() -> None:
    result = compare_synthetic_probe_evidence({}, {})

    assert result["state"] == "unavailable"
    assert result["comparable"] == 0
    assert result["mismatches"] == []
