"""Regression tests for TrueNAS stale-if-error status semantics."""

from nabla.api import homelab_health


def test_connect_timeout_with_stale_last_good_is_warning_not_failure() -> None:
    state = homelab_health._truenas_state(
        {"state": "ok"},
        None,
        {
            "reachable": False,
            "stage": "connect_timeout",
            "stale": True,
            "last_good": {"version": "26.0.0"},
        },
    )

    assert state == "warn"


def test_fresh_authenticated_api_failure_remains_failure() -> None:
    state = homelab_health._truenas_state(
        {"state": "ok"},
        None,
        {"reachable": False, "stage": "authentication", "stale": False},
    )

    assert state == "fail"
