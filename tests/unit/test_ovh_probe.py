"""The optional OVH SDK must not be required to import the application."""

from __future__ import annotations

import importlib
import sys

import pytest

from nabla.api.auth import openstack

_CREDENTIALS = ("OVH_APPLICATION_KEY", "OVH_APPLICATION_SECRET", "OVH_CONSUMER_KEY")


def test_module_imports_without_ovh_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    # ``None`` in sys.modules makes ``import ovh`` raise ImportError, like the
    # minimal FastAPI runtime installed with ``uv sync --no-default-groups``.
    monkeypatch.setitem(sys.modules, "ovh", None)
    monkeypatch.setitem(sys.modules, "ovh.exceptions", None)

    reloaded = importlib.reload(openstack)

    assert callable(reloaded.probe_ovh_me_reachable)


def test_probe_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OVH_API_PROBE_ENABLED", raising=False)
    for name in _CREDENTIALS:
        monkeypatch.setenv(name, "dummy-value")

    out = openstack.probe_ovh_me_reachable()

    assert out["reachable"] is None
    assert out["skipped"] is True
    assert "OVH_API_PROBE_ENABLED" in out["reason"]


def test_probe_skips_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OVH_API_PROBE_ENABLED", "true")
    for name in _CREDENTIALS:
        monkeypatch.delenv(name, raising=False)

    out = openstack.probe_ovh_me_reachable()

    assert out["reachable"] is None
    assert out["skipped"] is True


def test_probe_reports_missing_sdk_as_configuration_not_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OVH_API_PROBE_ENABLED", "true")
    for name in _CREDENTIALS:
        monkeypatch.setenv(name, "dummy-value")
    monkeypatch.setattr(openstack, "_ovh_sdk_installed", lambda: False)

    out = openstack.probe_ovh_me_reachable()

    assert out["reachable"] is None
    assert out["skipped"] is True
    assert "db" in out["reason"]
    assert "dummy-value" not in str(out)
