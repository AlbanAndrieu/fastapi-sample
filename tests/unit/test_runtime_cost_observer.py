"""Owner-only and low-overhead process observation contracts."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import Mock

from nabla.api import runtime_cost_observer
from nabla.route_policy import Credential, Visibility, route_policy_for
from nabla.routes import _register_runtime_resource_observer


def test_process_sample_uses_cumulative_cpu_time_without_fake_utilization(monkeypatch):
    process = Mock()
    process.memory_info.return_value = SimpleNamespace(rss=104_857_600)
    process.cpu_times.return_value = SimpleNamespace(user=1.25, system=0.75)
    process.num_threads.return_value = 3
    context = Mock()
    context.__enter__ = Mock(return_value=process)
    context.__exit__ = Mock(return_value=False)
    process.oneshot.return_value = context
    monkeypatch.setattr(runtime_cost_observer.psutil, "Process", lambda: process)

    result = runtime_cost_observer.snapshot_process_resources()
    assert result["rss_bytes"] == 104_857_600
    assert result["process_cpu_seconds_total"] == 2.0
    assert result["threads"] == 3
    assert result["cpu_utilization_percent"] is None
    assert result["billing_usage"] is None
    assert result["replica_count"] is None
    assert "HOSTNAME" not in str(result)


def test_process_sample_is_not_a_public_endpoint():
    policy = route_policy_for("/api/runtime/resources")
    assert policy.visibility is Visibility.OWNER
    assert policy.credential is Credential.DIAGNOSTICS_KEY


def test_anonymous_client_cannot_read_process_metrics(monkeypatch):
    monkeypatch.setattr("nabla.routes.owner_ui_authenticated", lambda *_: False)
    monkeypatch.setattr("nabla.routes.get_settings", lambda: object())
    app = FastAPI()
    _register_runtime_resource_observer(app)
    with TestClient(app) as client:
        response = client.get("/api/runtime/resources")
    assert response.status_code == 403
    assert "rss_bytes" not in response.text
    assert response.headers["cache-control"] == "private, no-store"


def test_owner_receives_one_bounded_snapshot_without_metrics_loop(monkeypatch):
    monkeypatch.setattr("nabla.routes.owner_ui_authenticated", lambda *_: True)
    monkeypatch.setattr("nabla.routes.get_settings", lambda: object())
    read = Mock(return_value={
        "schema_version": 1,
        "model": "process-resource-observation",
        "rss_bytes": 1024,
        "process_cpu_seconds_total": 2.0,
    })
    monkeypatch.setattr(runtime_cost_observer, "snapshot_process_resources", read)
    app = FastAPI()
    _register_runtime_resource_observer(app)
    with TestClient(app) as client:
        response = client.get("/api/runtime/resources")
    assert response.status_code == 200
    assert response.json()["rss_bytes"] == 1024
    assert response.headers["cache-control"] == "private, no-store"
    read.assert_called_once_with()
