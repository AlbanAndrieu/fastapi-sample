"""Tests for the normalized multidimensional service health contract."""

from nabla.api.service_health_model import build_health_model, normalize_health_state


def test_health_model_normalizes_every_axis() -> None:
    assert build_health_model(
        service_state="OK",
        transport_state="warn",
        authentication_state=None,
        application_state="FAIL",
        runtime_state="running",
        dependency_state="ok",
        effective_state="warn",
    ) == {
        "service_state": "ok",
        "transport_state": "warn",
        "authentication_state": "unknown",
        "application_state": "fail",
        "runtime_state": "unknown",
        "dependency_state": "ok",
        "effective_state": "warn",
    }


def test_unknown_provider_state_does_not_leak_into_contract() -> None:
    assert normalize_health_state("RUNNING") == "unknown"
    assert normalize_health_state("CRASHED") == "unknown"
