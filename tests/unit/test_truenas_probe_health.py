"""Contract tests for pure TrueNAS target/state reconciliation."""

import pytest

from nabla.api import homelab_health
from nabla.api.homelab_models import HomelabService


def test_truenas_internal_target_prefers_explicit_configuration(monkeypatch) -> None:
    services = [HomelabService(name="App", internalHost="172.17.0.24", internalPort=80)]
    monkeypatch.setenv("TRUENAS_URL", "https://192.168.1.24:8443")

    assert homelab_health._truenas_internal_target(services) == (
        "192.168.1.24",
        8443,
    )


def test_truenas_internal_target_uses_public_default(monkeypatch) -> None:
    services = [
        HomelabService(name="Other", internalHost="172.17.0.20", internalPort=80),
        HomelabService(name="App", internalHost="172.17.0.24", internalPort=8080),
    ]
    monkeypatch.delenv("TRUENAS_URL", raising=False)

    assert homelab_health._truenas_internal_target(services) == (
        "truenas.albandrieu.com",
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
