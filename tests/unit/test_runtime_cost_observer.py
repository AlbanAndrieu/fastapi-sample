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
    monkeypatch.setattr("nabla.routes.get_settings", object)
    app = FastAPI()
    _register_runtime_resource_observer(app)
    with TestClient(app) as client:
        response = client.get("/api/runtime/resources")
    assert response.status_code == 403
    assert "rss_bytes" not in response.text
    assert response.headers["cache-control"] == "private, no-store"


def test_owner_receives_one_bounded_snapshot_without_metrics_loop(monkeypatch):
    monkeypatch.setattr("nabla.routes.owner_ui_authenticated", lambda *_: True)
    monkeypatch.setattr("nabla.routes.get_settings", object)
    read = Mock(
        return_value={
            "schema_version": 1,
            "model": "process-resource-observation",
            "rss_bytes": 1024,
            "process_cpu_seconds_total": 2.0,
        },
    )
    monkeypatch.setattr(runtime_cost_observer, "snapshot_process_resources", read)
    app = FastAPI()
    _register_runtime_resource_observer(app)
    with TestClient(app) as client:
        response = client.get("/api/runtime/resources")
    assert response.status_code == 200
    assert response.json()["rss_bytes"] == 1024
    assert response.headers["cache-control"] == "private, no-store"
    read.assert_called_once_with()


def test_cgroup_v2_owner_sample_reads_real_limits_without_network(monkeypatch):
    values = {
        "memory.current": str(420 * 1024 * 1024),
        "memory.max": str(500 * 1024 * 1024),
        "cpu.max": "10000 100000",
        "cpu.stat": "usage_usec 12345678\nnr_periods 7",
        "memory.events": "oom 2\noom_kill 1\n",
    }
    monkeypatch.setattr(
        runtime_cost_observer,
        "_read_cgroup_file",
        lambda name: values.get(name),
    )
    result = runtime_cost_observer.snapshot_cgroup_resources()
    assert result["memory_current_bytes"] == 420 * 1024 * 1024
    assert result["memory_limit_bytes"] == 500 * 1024 * 1024
    assert result["memory_limit_percent"] == 84.0
    assert result["cpu_quota_cores"] == 0.1
    assert result["cpu_usage_seconds_total"] == 12.3457
    assert result["oom_kill_count"] == 1
    assert "cpu_utilization_percent" not in result
    assert "billing_usage" not in result


def test_cgroup_missing_and_unlimited_are_unknown_not_zero(monkeypatch):
    values = {
        "memory.current": "1000",
        "memory.max": "max",
        "cpu.max": "max 100000",
        "cpu.stat": "usage_usec NaN",
    }
    monkeypatch.setattr(
        runtime_cost_observer,
        "_read_cgroup_file",
        lambda name: values.get(name),
    )
    result = runtime_cost_observer.snapshot_cgroup_resources()
    assert result["memory_current_bytes"] == 1000
    assert result["memory_limit_bytes"] is None
    assert result["memory_limit_percent"] is None
    assert result["cpu_quota_cores"] is None
    assert result["cpu_usage_seconds_total"] is None
    assert result["oom_kill_count"] is None


def test_cgroup_rejects_malformed_and_oversized_values(monkeypatch):
    values = {
        "memory.current": "-1",
        "memory.max": "9" * 150,
        "cpu.max": "nope zero",
        "cpu.stat": "usage_usec Inf\nother 10",
        "memory.events": "oom_kill -1",
    }
    monkeypatch.setattr(
        runtime_cost_observer,
        "_read_cgroup_file",
        lambda name: values.get(name),
    )
    result = runtime_cost_observer.snapshot_cgroup_resources()
    assert result["memory_current_bytes"] is None
    assert result["memory_limit_bytes"] is None
    assert result["memory_limit_percent"] is None
    assert result["cpu_quota_cores"] is None
    assert result["cpu_usage_seconds_total"] is None
    assert result["oom_kill_count"] is None


def test_process_snapshot_keeps_billing_unknown_when_cgroup_available(monkeypatch):
    monkeypatch.setattr(
        runtime_cost_observer,
        "snapshot_cgroup_resources",
        lambda: {"memory_current_bytes": 100, "memory_limit_percent": 20},
    )
    process = Mock()
    process.memory_info.return_value = SimpleNamespace(rss=90)
    process.cpu_times.return_value = SimpleNamespace(user=3.0, system=2.0)
    process.num_threads.return_value = 1
    context = Mock()
    context.__enter__ = Mock(return_value=process)
    context.__exit__ = Mock(return_value=False)
    process.oneshot.return_value = context
    monkeypatch.setattr(runtime_cost_observer.psutil, "Process", lambda: process)
    result = runtime_cost_observer.snapshot_process_resources()
    assert result["cgroup"]["memory_limit_percent"] == 20
    assert result["billing_usage"] is None
    assert result["cpu_utilization_percent"] is None


def test_cgroup_file_reads_are_bounded_and_allowlisted(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_cost_observer, "_CGROUP_DIR", tmp_path)
    (tmp_path / "memory.current").write_text("100", encoding="ascii")
    (tmp_path / "memory.max").write_text("9" * 5000, encoding="ascii")
    assert runtime_cost_observer._read_cgroup_file("memory.current") == "100"
    assert runtime_cost_observer._read_cgroup_file("memory.max") is None
    assert runtime_cost_observer._read_cgroup_file("etc/passwd") is None
    assert runtime_cost_observer._read_cgroup_file("missing") is None
