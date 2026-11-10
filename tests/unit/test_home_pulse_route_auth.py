"""Owner-only appliance pulse endpoint: no public rollback, no parameters."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nabla.route_policy import Credential, Visibility, route_policy_for
from nabla.routes import _register_appliance_pulse


def test_pulse_requires_diagnostics_route_policy() -> None:
    policy = route_policy_for("/api/home/appliance/pulse")
    assert policy.visibility is Visibility.OWNER
    assert policy.credential is Credential.DIAGNOSTICS_KEY


def test_pulse_denies_anonymous_before_any_truenas_call(monkeypatch) -> None:
    monkeypatch.setattr("nabla.routes.owner_ui_authenticated", lambda *_args: False)
    monkeypatch.setattr("nabla.routes.get_settings", object)
    app = FastAPI()
    _register_appliance_pulse(app)
    with TestClient(app) as client:
        response = client.get("/api/home/appliance/pulse")
    assert response.status_code == 403
    assert response.headers["cache-control"] == "private, no-store"


def test_pulse_owner_gets_payload_and_parameters_are_rejected(monkeypatch) -> None:
    monkeypatch.setattr("nabla.routes.owner_ui_authenticated", lambda *_args: True)
    monkeypatch.setattr("nabla.routes.get_settings", object)

    async def result() -> dict:
        return {"model": "owner-appliance-pulse", "state": "observed"}

    monkeypatch.setattr("nabla.api.home_appliance_pulse.fetch_appliance_pulse", result)
    app = FastAPI()
    _register_appliance_pulse(app)
    with TestClient(app) as client:
        ok = client.get("/api/home/appliance/pulse")
        rejected = client.get("/api/home/appliance/pulse", params={"method": "system.shutdown"})
    assert ok.status_code == 200 and ok.json()["model"] == "owner-appliance-pulse"
    assert ok.headers["x-robots-tag"] == "noindex, nofollow"
    assert rejected.status_code == 422
