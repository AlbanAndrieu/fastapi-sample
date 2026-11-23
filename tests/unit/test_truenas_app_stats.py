"""F07 per-App resources from the TrueNAS app.stats event source (offline fakes)."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from nabla.api import topology_telemetry, truenas_app_stats as stats


def test_projection_converts_host_cpu_percent_and_keeps_stopped_apps_valueless() -> None:
    rows = [
        {
            "app_name": "paperless",
            "cpu_usage": 12.5,
            "memory": 536870912,
            "networks": [{"rx_bytes": 1000, "tx_bytes": 500}, {"rx_bytes": 24, "tx_bytes": 0}],
            "blkio": {"read": 4096, "write": 8192},
        },
        {"app_name": "bitcoind", "cpu_usage": 0, "memory": 0, "networks": [], "blkio": {"read": 0, "write": 0}},
        {"app_name": "broken", "cpu_usage": float("nan"), "memory": -1, "networks": [{"rx_bytes": "x", "tx_bytes": 1}]},
        {"app_name": "paperless", "cpu_usage": 99},
        "not-a-row",
    ]

    apps = stats.project_app_stats(rows, cores=8)

    assert apps["paperless"] == {
        "running": True,
        "cpu_host_percent": 12.5,
        "cpu_cores": 1.0,
        "memory_bytes": 536870912.0,
        "rx_bytes_per_second": 1024.0,
        "tx_bytes_per_second": 500.0,
        "network_bytes_per_second": 1524.0,
        "blkio_read_bytes_total": 4096.0,
        "blkio_write_bytes_total": 8192.0,
    }
    assert apps["bitcoind"] == {"running": False}
    assert apps["broken"]["cpu_cores"] is None and apps["broken"]["memory_bytes"] is None
    assert apps["broken"]["rx_bytes_per_second"] is None and apps["broken"]["network_bytes_per_second"] is None
    assert stats.project_app_stats(rows, cores=None)["paperless"]["cpu_cores"] is None


class _FakeClient:
    def __init__(self, fields, *, emit=True):
        self.fields, self.emit, self.unsubscribed = fields, emit, []

    def call(self, method, *args):
        assert method == "system.info"
        return {"cores": 4}

    def subscribe(self, name, callback):
        assert name == "app.stats"
        if self.emit:
            callback("ADDED", collection="app.stats", msg="added", fields=self.fields)
        return "sub-1"

    def unsubscribe(self, subscription):
        self.unsubscribed.append(subscription)


class _FakeAdapter:
    def __init__(self, client):
        self.client = client

    @contextmanager
    def read_only_session(self, *, call_timeout):
        assert call_timeout == stats.CALL_TIMEOUT_SECONDS
        yield self.client


def test_collect_takes_one_sample_and_always_unsubscribes(monkeypatch) -> None:
    client = _FakeClient([{"app_name": "redis", "cpu_usage": 50, "memory": 1, "networks": [{"rx_bytes": 1, "tx_bytes": 1}]}])
    collected = stats.collect_app_stats(_FakeAdapter(client))
    assert collected["state"] == "observed" and collected["cores"] == 4
    assert collected["apps"]["redis"]["cpu_cores"] == 2.0
    assert client.unsubscribed == ["sub-1"]

    monkeypatch.setattr(stats, "FIRST_EVENT_SECONDS", 0.01)
    silent = _FakeClient([], emit=False)
    assert stats.collect_app_stats(_FakeAdapter(silent)) == {"state": "telemetry_unavailable", "reason": "no_event"}
    assert silent.unsubscribed == ["sub-1"]


@pytest.mark.asyncio
async def test_fetch_is_not_configured_without_credentials_and_caches_samples(monkeypatch) -> None:
    stats.reset_app_stats_cache()
    monkeypatch.setattr(stats, "build_truenas_adapter", lambda: None)
    assert (await stats.fetch_app_stats())["state"] == "not_configured"

    calls = []
    monkeypatch.setattr(stats, "collect_app_stats", lambda adapter: calls.append(adapter) or {"state": "observed", "cores": 2, "apps": {}})
    first = await stats.fetch_app_stats(adapter=object())
    second = await stats.fetch_app_stats(adapter=object())
    assert (first["cached"], second["cached"], len(calls)) == (False, True, 1)
    stats.reset_app_stats_cache()


@pytest.mark.asyncio
async def test_fetch_turns_errors_into_evidence(monkeypatch) -> None:
    stats.reset_app_stats_cache()

    def denied(_adapter):
        raise PermissionError("APPS_READ missing")

    monkeypatch.setattr(stats, "collect_app_stats", denied)
    payload = await stats.fetch_app_stats(adapter=object(), use_cache=False)
    assert payload["state"] == "telemetry_unavailable" and payload["reason"] == "PermissionError"
    assert payload["apps"] == {}


@pytest.mark.asyncio
async def test_topology_falls_back_to_app_stats_only_without_container_series(monkeypatch) -> None:
    async def sample():
        return {
            "state": "observed",
            "observed_at": "2026-11-22T20:00:00Z",
            "apps": {
                "paperless": {"running": True, "cpu_cores": 0.5, "memory_bytes": 10.0},
                "redis": {"running": True, "cpu_cores": None, "cpu_host_percent": 25.0, "memory_bytes": 1.0},
                "bitcoind": {"running": False},
            },
        }

    monkeypatch.setattr(topology_telemetry, "fetch_app_stats", sample)
    value = {
        "state": "telemetry_unavailable",
        "resource_source": "truenas_cadvisor",
        "host_cpu_cores": 16,
        "resources": {"paperless": {"zfs_dataset_bytes": 7.0}},
    }

    merged = await topology_telemetry._with_app_stats(value)

    assert merged["resource_source"] == "truenas_app_stats"
    assert merged["resource_granularity"] == "truenas_app"
    assert merged["state"] == "partial"
    assert merged["resources"]["paperless"]["zfs_dataset_bytes"] == 7.0
    assert merged["resources"]["paperless"]["cpu_cores"] == 0.5
    assert "bitcoind" not in merged["resources"]
    # system.info is EACCES for the observer key: cores come from node_exporter.
    assert merged["resources"]["redis"]["cpu_cores"] == 4.0
    assert topology_telemetry._has_container_signals({"x": {"zfs_dataset_bytes": 1}}) is False
    assert topology_telemetry._has_container_signals({"x": {"cpu_cores": 0.0}}) is True
