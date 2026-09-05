"""Tests for sanitized application runtime/egress topology evidence."""

import pytest

from nabla.api import runtime_topology


@pytest.mark.asyncio
async def test_local_runtime_snapshot_is_explicitly_not_platform_replica_count(
    monkeypatch,
) -> None:
    monkeypatch.setenv("HOSTNAME", "container-a")
    monkeypatch.delenv("FASTAPI_CLOUD", raising=False)

    async def egress():
        return {
            "ip": "34.200.20.162",
            "observed": True,
            "cached": False,
            "source": "external_echo",
        }

    monkeypatch.setattr(runtime_topology, "observe_public_egress_ip", egress)

    snapshot = await runtime_topology.build_runtime_topology_snapshot(None)

    assert snapshot["provider"] == "Local workstation"
    assert snapshot["runtime_mode"] == "local"
    assert snapshot["observed_instance_count"] == 1
    assert snapshot["platform_replica_count"] is None
    assert snapshot["platform_replica_count_available"] is False
    assert snapshot["aggregation"] == "local_only"
    assert snapshot["degraded"] is False
    assert snapshot["active_egress_ips"] == ["34.200.20.162"]
    assert snapshot["recent_egress_ips"] == ["34.200.20.162"]
    assert "local workstation" in snapshot["count_semantics"]
    assert snapshot["instances"][0]["id"].startswith("runtime-")
    assert "container-a" not in str(snapshot)


@pytest.mark.asyncio
async def test_fastapi_cloud_runtime_snapshot_keeps_cloud_semantics(monkeypatch) -> None:
    monkeypatch.setenv("HOSTNAME", "container-cloud")
    monkeypatch.setenv("FASTAPI_CLOUD", "1")

    async def egress():
        return {
            "ip": "52.1.10.241",
            "observed": True,
            "cached": True,
            "source": "external_echo",
        }

    monkeypatch.setattr(runtime_topology, "observe_public_egress_ip", egress)

    snapshot = await runtime_topology.build_runtime_topology_snapshot(None)

    assert snapshot["provider"] == "FastAPI Cloud"
    assert snapshot["runtime_mode"] == "fastapi_cloud"
    assert snapshot["degraded"] is True
    assert "not the FastAPI Cloud control-plane replica count" in snapshot["count_semantics"]


def test_runtime_instance_id_is_stable_and_opaque(monkeypatch) -> None:
    monkeypatch.setenv("HOSTNAME", "container-a")
    first = runtime_topology.runtime_instance_id()
    second = runtime_topology.runtime_instance_id()

    assert first == second
    assert first.startswith("runtime-")
    assert "container-a" not in first



def test_runtime_registry_keys_isolate_local_and_cloud_heartbeats() -> None:
    local = runtime_topology.runtime_registry_keys("local")
    cloud = runtime_topology.runtime_registry_keys("fastapi_cloud")

    assert local != cloud
    assert all(":local:" in key for key in local)
    assert all(":fastapi_cloud:" in key for key in cloud)
    assert all(not key.endswith(":runtime:instances:last-seen") for key in (*local, *cloud))
