"""Tests for sanitized application runtime/egress topology evidence."""

from unittest.mock import AsyncMock

import pytest

from nabla.api import runtime_topology


@pytest.mark.asyncio
async def test_local_runtime_snapshot_is_explicitly_not_platform_replica_count(
    monkeypatch,
) -> None:
    monkeypatch.setenv("HOSTNAME", "container-a")
    monkeypatch.delenv("FASTAPI_CLOUD", raising=False)
    monkeypatch.delenv("FASTAPI_CLOUD_APP_ID", raising=False)
    monkeypatch.delenv("SICKZ_NETWORK_LABEL", raising=False)
    monkeypatch.delenv("AWS_EXECUTION_ENV", raising=False)

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



@pytest.mark.asyncio
async def test_redis_usage_snapshot_reports_safe_capacity_metrics() -> None:
    client = AsyncMock()
    client.info.side_effect = [
        {
            "used_memory": 1_048_576,
            "used_memory_human": "1.00M",
            "used_memory_rss": 2_097_152,
            "used_memory_rss_human": "2.00M",
            "used_memory_peak": 1_572_864,
            "used_memory_peak_human": "1.50M",
            "maxmemory": 4_194_304,
            "maxmemory_human": "4.00M",
            "maxmemory_policy": "allkeys-lru",
            "mem_fragmentation_ratio": 2.0,
        },
        {"connected_clients": 4, "blocked_clients": 1},
        {
            "instantaneous_ops_per_sec": 12,
            "keyspace_hits": 40,
            "keyspace_misses": 2,
            "evicted_keys": 3,
            "expired_keys": 9,
        },
    ]
    client.dbsize.return_value = 37

    result = await runtime_topology.redis_usage_snapshot(client)

    assert result["configured"] is True
    assert result["available"] is True
    assert result["telemetry_available"] is True
    assert result["used_memory_bytes"] == 1_048_576
    assert result["memory_utilization_percent"] == 25.0
    assert result["connected_clients"] == 4
    assert result["keys"] == 37
    assert result["instantaneous_ops_per_sec"] == 12


@pytest.mark.asyncio
async def test_redis_usage_snapshot_is_optional_without_client() -> None:
    result = await runtime_topology.redis_usage_snapshot(None)

    assert result["configured"] is False
    assert result["available"] is False
    assert result["telemetry_available"] is False

@pytest.mark.asyncio
async def test_redis_usage_snapshot_keeps_ping_health_when_info_is_forbidden() -> None:
    client = AsyncMock()
    client.ping.return_value = True
    client.info.side_effect = PermissionError("INFO not permitted")

    result = await runtime_topology.redis_usage_snapshot(client)

    assert result["configured"] is True
    assert result["available"] is True
    assert result["telemetry_available"] is False
    assert result["failure_stage"] == "info"
    assert result["exception_type"] == "PermissionError"
    assert "not permitted" not in str(result)


def test_runtime_registry_keys_isolate_local_and_cloud_heartbeats() -> None:
    local = runtime_topology.runtime_registry_keys("local")
    cloud = runtime_topology.runtime_registry_keys("fastapi_cloud")

    assert local != cloud
    assert all(":local:" in key for key in local)
    assert all(":fastapi_cloud:" in key for key in cloud)
    assert all(not key.endswith(":runtime:instances:last-seen") for key in (*local, *cloud))
