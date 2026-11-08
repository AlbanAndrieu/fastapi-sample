"""Owner-only historical endpoint is not a public diagnostics rollback."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from nabla.route_policy import Credential, Visibility, route_policy_for
from nabla.routes import _register_operations_history


def test_history_requires_diagnostics_route_policy() -> None:
    policy = route_policy_for("/api/home/metrics/history")
    assert policy.visibility is Visibility.OWNER
    assert policy.credential is Credential.DIAGNOSTICS_KEY


def test_history_denies_anonymous_before_any_prometheus_request(monkeypatch) -> None:
    monkeypatch.setattr(
        "nabla.routes.owner_ui_authenticated", lambda *_args: False
    )
    monkeypatch.setattr("nabla.routes.get_settings", lambda: object())
    app = FastAPI()
    _register_operations_history(app)
    with TestClient(app) as client:
        response = client.get("/api/home/metrics/history")
    assert response.status_code == 403
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize("window", ["1h", "24h", "7d"])
def test_history_owner_can_use_bounded_windows(monkeypatch, window: str) -> None:
    monkeypatch.setattr(
        "nabla.routes.owner_ui_authenticated", lambda *_args: True
    )

    async def result(asked: str) -> dict:
        assert asked == window
        return {"model": "owner-operations-history", "window": asked}

    monkeypatch.setattr(
        "nabla.api.home_metrics_history.fetch_home_metrics_history", result
    )
    monkeypatch.setattr("nabla.routes.get_settings", lambda: object())
    app = FastAPI()
    _register_operations_history(app)
    with TestClient(app) as client:
        response = client.get(
            "/api/home/metrics/history", params={"window": window}
        )
    assert response.status_code == 200
    assert response.json()["window"] == window


def test_history_never_accepts_query_or_arbitrary_window(monkeypatch) -> None:
    monkeypatch.setattr(
        "nabla.routes.owner_ui_authenticated", lambda *_args: True
    )
    monkeypatch.setattr("nabla.routes.get_settings", lambda: object())
    app = FastAPI()
    _register_operations_history(app)
    with TestClient(app) as client:
        response = client.get(
            "/api/home/metrics/history", params={"window": "365d"}
        )
    assert response.status_code == 422
    assert "metrics" not in str(response.json())
