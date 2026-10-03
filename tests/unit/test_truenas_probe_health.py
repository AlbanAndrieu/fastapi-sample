"""Contract tests for pure TrueNAS target/state reconciliation."""

import pytest

from nabla.api import homelab_health


def test_truenas_internal_target_uses_explicit_lan_configuration(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TRUENAS_LAN_HOST", "192.168.1.24")
    monkeypatch.setenv("TRUENAS_LAN_PORT", "8443")

    assert homelab_health._truenas_internal_target() == (
        "192.168.1.24",
        8443,
    )


def test_truenas_internal_target_defaults_to_lan_listener(monkeypatch) -> None:
    monkeypatch.delenv("TRUENAS_LAN_HOST", raising=False)
    monkeypatch.delenv("TRUENAS_LAN_PORT", raising=False)

    assert homelab_health._truenas_internal_target() == (
        "172.17.0.24",
        7000,
    )


@pytest.mark.parametrize(
    ("public_state", "internal_state", "expected"),
    [
        ("ok", None, "ok"),
        ("ok", "ok", "ok"),
        ("ok", "fail", "warn"),
        ("warn", None, "warn"),
        ("fail", "ok", "warn"),
        ("fail", "fail", "fail"),
        ("fail", None, "fail"),
    ],
)
def test_truenas_state_distinguishes_host_and_ingress_failures(
    public_state: str,
    internal_state: str | None,
    expected: str,
) -> None:
    public = {"state": public_state}
    internal = {"state": internal_state} if internal_state is not None else None

    assert homelab_health._truenas_state(public, internal) == expected


def test_truenas_api_failure_degrades_but_does_not_hide_https_liveness() -> None:
    assert (
        homelab_health._truenas_state(
            {"state": "ok"},
            None,
            {"reachable": False},
        )
        == "warn"
    )


def test_truenas_api_failure_remains_failure_when_https_is_down() -> None:
    assert (
        homelab_health._truenas_state(
            {"state": "fail"},
            None,
            {"reachable": False},
        )
        == "fail"
    )


def test_appliance_can_be_healthy_while_public_ingress_is_down() -> None:
    public = {"state": "fail"}
    api = {"reachable": True}
    diagnostics = {
        "stages": [
            {"id": "socket", "state": "ok"},
            {"id": "tls", "state": "fail"},
        ],
    }

    assert (
        homelab_health.truenas_probe_health.truenas_appliance_state(
            public,
            None,
            api,
        )
        == "ok"
    )
    assert (
        homelab_health.truenas_probe_health.truenas_public_ingress_state(
            public,
            diagnostics,
        )
        == "fail"
    )


def test_public_ingress_conflict_is_warning_when_http_and_raw_tls_disagree() -> None:
    diagnostics = {
        "stages": [
            {"id": "socket", "state": "ok"},
            {"id": "tls", "state": "fail"},
        ],
    }

    assert (
        homelab_health.truenas_probe_health.truenas_public_ingress_state(
            {"state": "ok"},
            diagnostics,
        )
        == "warn"
    )


def test_wan_tls_keeps_overall_state_degraded_when_http_fails() -> None:
    public = {"state": "fail"}

    assert (
        homelab_health._truenas_state(
            public,
            None,
            {"reachable": False},
            wan_tls_reachable=True,
        )
        == "warn"
    )
    assert (
        homelab_health._truenas_state(
            public,
            None,
            {"reachable": False},
            wan_tls_reachable=False,
        )
        == "fail"
    )
