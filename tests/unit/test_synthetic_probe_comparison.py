"""Tests for internal direct-vs-Gatus probe reconciliation."""

from nabla.api.synthetic_probe_comparison import (
    compare_internal_probe_evidence,
    evaluate_internal_probe_delegation,
)


def _platform(services: dict) -> dict:
    return {
        "configured": True,
        "synthetic_probes": {
            "source": "gatus_via_prometheus",
            "shadow_only": True,
            "state": "observed",
            "gatus_up": 1.0,
            "services": services,
        },
    }


def test_public_outside_in_probes_are_not_compared_to_internal_gatus() -> None:
    homelab = {
        "public_probe_results": [
            {"id": "garage", "state": "fail"},
            {"id": "vaultwarden", "state": "ok"},
        ],
        "internal_services": [
            {"id": "nexus", "state": "ok"},
        ],
    }
    platform = _platform(
        {
            "garage": {"HTTP": {"success": 1.0}},
            "vaultwarden": {"HTTP": {"success": 1.0}},
            "nexus": {"TCP": {"success": 1.0}},
        }
    )

    result = compare_internal_probe_evidence(homelab, platform)

    assert result["external_probes_preserved"] is True
    assert result["scope"] == "truenas_internal_only"
    assert result["comparable"] == 1
    assert result["matched"] == 1
    assert result["mismatched"] == 0


def test_internal_http_gatus_is_stronger_evidence_not_transport_mismatch() -> None:
    homelab = {
        "internal_services": [
            {"id": "fastapi-sample", "state": "ok"},
            {"id": "prometheus", "state": "ok"},
        ],
    }
    platform = _platform(
        {
            "fastapi-sample": {"HTTP": {"success": 1.0}},
            "prometheus": {"HTTP": {"success": 0.0}},
        }
    )

    result = compare_internal_probe_evidence(homelab, platform)

    assert result["comparable"] == 0
    assert result["application_evidence"] == 2
    assert result["mismatched"] == 0
    assert result["missing_gatus"] == 0


def test_internal_tcp_mismatch_is_reported() -> None:
    homelab = {
        "internal_services": [
            {"id": "nexus", "state": "ok"},
            {"id": "missing", "state": "fail"},
        ],
    }
    platform = _platform(
        {
            "nexus": {"TCP": {"success": 0.0}},
        }
    )

    result = compare_internal_probe_evidence(homelab, platform)

    assert result["comparable"] == 1
    assert result["matched"] == 0
    assert result["mismatched"] == 1
    assert result["missing_gatus"] == 1
    assert result["mismatches"] == [
        {
            "id": "nexus",
            "direct_state": "ok",
            "gatus_type": "TCP",
            "gatus_success": 0.0,
        }
    ]


def test_internal_comparison_is_unavailable_without_synthetic_services() -> None:
    result = compare_internal_probe_evidence({}, {})

    assert result["state"] == "unavailable"
    assert result["external_probes_preserved"] is True
    assert result["comparable"] == 0


def test_internal_delegation_reports_configuration_and_coverage_blockers() -> None:
    result = evaluate_internal_probe_delegation(
        {
            "configured": False,
            "synthetic_probes": {
                "state": "not_configured",
                "gatus_up": None,
            },
        },
        {
            "comparable": 0,
            "application_evidence": 0,
            "mismatched": 0,
            "missing_gatus": 2,
        },
    )

    assert result["candidate"] is False
    assert result["external_probes_preserved"] is True
    assert result["blockers"] == [
        "prometheus_not_configured",
        "gatus_not_observed",
        "no_internal_gatus_evidence",
        "missing_internal_gatus_evidence",
    ]


def test_internal_delegation_candidate_preserves_external_probe_strategy() -> None:
    result = evaluate_internal_probe_delegation(
        _platform({}),
        {
            "comparable": 5,
            "application_evidence": 7,
            "mismatched": 0,
            "missing_gatus": 0,
        },
    )

    assert result == {
        "provider": "gatus_via_prometheus",
        "scope": "truenas_internal_generic_only",
        "external_probe_strategy": "fastapi_cloud_embedded_outside_in",
        "external_probes_preserved": True,
        "state": "candidate",
        "candidate": True,
        "requires_observation_window": True,
        "blockers": [],
        "comparable": 5,
        "application_evidence": 7,
        "mismatched": 0,
        "missing_gatus": 0,
    }


def test_internal_delegation_blocks_same_protocol_transport_mismatch() -> None:
    result = evaluate_internal_probe_delegation(
        _platform({}),
        {
            "comparable": 4,
            "application_evidence": 3,
            "mismatched": 1,
            "missing_gatus": 0,
        },
    )

    assert result["candidate"] is False
    assert result["blockers"] == ["internal_transport_mismatches"]


def test_invalid_gatus_samples_are_not_treated_as_success() -> None:
    """A NaN, infinity, or boolean must never make a service look healthy."""
    for invalid in (float("nan"), float("inf"), -1.0, 2.0, True):
        homelab = {"internal_services": [{"id": "nexus", "state": "ok"}]}
        result = compare_internal_probe_evidence(
            homelab,
            _platform({"nexus": {"TCP": {"success": invalid}}}),
        )
        assert result["comparable"] == 0
        assert result["missing_gatus"] == 1


def test_invalid_gatus_up_blocks_delegation() -> None:
    """Only a finite numeric proof may authorize internal delegation."""
    for invalid in (float("nan"), float("inf"), True, None):
        platform = _platform({})
        platform["synthetic_probes"]["gatus_up"] = invalid
        result = evaluate_internal_probe_delegation(
            platform,
            {"comparable": 1, "application_evidence": 0, "mismatched": 0, "missing_gatus": 0},
        )
        assert result["candidate"] is False
        assert "gatus_not_up" in result["blockers"]
