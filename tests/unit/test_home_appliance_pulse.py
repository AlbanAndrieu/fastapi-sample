"""Live TrueNAS appliance pulse: documented read-only calls, bounded, no invented values."""

from __future__ import annotations

from contextlib import contextmanager
import json
import time
from typing import Any

import pytest

from nabla.api import home_appliance_pulse as pulse
from nabla.integrations.truenas_client import TrueNASHealthProbeError

CANARY = "api-key-must-never-appear"
NOW = 1_762_600_000


def _netdata(name: str, legend: list[str], rows: list[list[float]], identifier: str | None = None) -> dict[str, Any]:
    return {"name": name, "identifier": identifier, "legend": legend, "data": rows, "start": rows[0][0], "end": rows[-1][0], "aggregations": {}}


def canned() -> dict[str, Any]:
    rows = [[NOW + 60 * index, 80.0 - index, 10.0, 10.0 + index] for index in range(5)]
    return {
        "system.info": {"version": "TrueNAS-27.0.0-RC.1", "cores": 8, "physmem": 64 * 1024**3, "uptime_seconds": 86400.5, "loadavg": [9.6, 4.0, 2.0]},
        "alert.list": [
            {
                "klass": "ZpoolCapacityWarning",
                "level": "WARNING",
                "dismissed": False,
                "datetime": "2026-11-08T20:00:00+00:00",
                "formatted": "<b>Space</b> usage for pool <i>cpool</i> is 86%",
                "args": {"secret": CANARY},
            },
            {"klass": "AppUpdate", "level": "INFO", "dismissed": True, "datetime": "2026-11-01T00:00:00+00:00", "text": "update available"},
        ],
        "pool.query": [
            {
                "name": "cpool",
                "status": "ONLINE",
                "healthy": True,
                "warning": True,
                "size": 1000,
                "allocated": 860,
                "free": 140,
                "fragmentation": "12%",
                "scan": {"function": "SCRUB", "state": "FINISHED", "percentage": 100.0},
            },
        ],
        "interface.query": [
            {"name": "eno1", "type": "PHYSICAL", "state": {"link_state": "LINK_STATE_UP"}},
            {"name": "eno2", "type": "PHYSICAL", "state": {"link_state": "LINK_STATE_DOWN"}},
            {"name": "br0", "type": "BRIDGE", "state": {"link_state": "LINK_STATE_UP"}},
        ],
        "app.query": [{"id": "zabbix", "state": "RUNNING"}, {"id": "graylog", "state": "STOPPED"}, {"id": "openrag", "state": "CRASHED"}],
        "reporting.netdata_graphs": [{"name": "interface", "vertical_label": "Bits/s", "identifiers": ["eno1", "eno2"]}, {"name": "cpu", "vertical_label": "Percentage"}],
        "reporting.netdata_get_data": [
            _netdata("cpu", ["time", "idle", "system", "user"], rows),
            _netdata("memory", ["time", "free", "used", "cached"], [[NOW + 60 * i, 20.0, 70.0, 10.0] for i in range(5)]),
            _netdata("interface", ["time", "received", "sent"], [[NOW + 60 * i, 1000.0, 500.0] for i in range(5)], "eno1"),
        ],
    }


class FakeClient:
    def __init__(self, answers: dict[str, Any], failures: set[str] | None = None) -> None:
        self.answers = answers
        self.failures = failures or set()
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def call(self, method: str, *params: Any) -> Any:
        self.calls.append((method, params))
        if method in self.failures:
            raise RuntimeError(f"{method} rejected: ERPC role missing {CANARY}")
        return self.answers[method]


class FakeAdapter:
    def __init__(self, client: FakeClient, *, session_error: Exception | None = None) -> None:
        self.client = client
        self.session_error = session_error

    @contextmanager
    def read_only_session(self, *, call_timeout: float | None = None):
        assert call_timeout == pulse.CALL_TIMEOUT_SECONDS
        if self.session_error is not None:
            raise self.session_error
        yield self.client


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    pulse.reset_appliance_pulse_cache()


def test_full_pulse_uses_documented_methods_and_derives_impacts() -> None:
    client = FakeClient(canned())
    payload = pulse.collect_appliance_pulse(FakeAdapter(client))

    methods = [method for method, _params in client.calls]
    assert methods == ["system.info", "alert.list", "pool.query", "interface.query", "app.query", "reporting.netdata_graphs", "reporting.netdata_get_data"]
    graphs, query = client.calls[-1][1]
    assert {"name": "interface", "identifier": "eno1"} in graphs
    assert {"name": "interface", "identifier": "eno2"} not in graphs  # link down: not scraped
    assert query == {"unit": "HOUR", "page": 1, "aggregate": True}

    assert payload["state"] == "observed"
    assert payload["appliance"]["load_per_core_1m"] == 1.2
    assert payload["cpu"]["busy_percent"] == 24.0 and payload["cpu"]["derivation"] == "100_minus_idle"
    assert payload["memory"]["used_percent"] == 70.0
    assert payload["network"]["throughput"] == 1500.0 and payload["network"]["vertical_label"] == "Bits/s"
    assert payload["network"]["links_down"] == ["eno2"]
    assert payload["storage"]["worst_used_percent"] == 86.0
    assert payload["storage"]["pools"][0]["fragmentation_percent"] == 12.0
    assert payload["alerts"] == {
        "state": "observed",
        "total": 2,
        "active": 1,
        "by_level": {"WARNING": 1},
        "items": [
            {"klass": "ZpoolCapacityWarning", "level": "WARNING", "dismissed": False, "since": "2026-11-08T20:00:00+00:00", "text": "Space usage for pool cpool is 86%"},
            {"klass": "AppUpdate", "level": "INFO", "dismissed": True, "since": "2026-11-01T00:00:00+00:00", "text": "update available"},
        ],
    }
    assert payload["apps"]["counts"] == {"RUNNING": 1, "STOPPED": 1, "CRASHED": 1}
    impacts = {impact["id"]: impact for impact in payload["impacts"]}
    assert impacts["storage_capacity"]["state"] == "warn" and impacts["storage_capacity"]["linked"] == ["ZpoolCapacityWarning"]
    assert impacts["cpu_pressure"]["state"] == "warn"
    assert impacts["memory_pressure"]["state"] == "ok" and impacts["memory_pressure"]["linked"] == ["openrag"]
    assert impacts["app_fleet"]["state"] == "fail"
    assert impacts["active_alerts"]["state"] == "warn"
    assert impacts["network_links"]["state"] == "warn" and impacts["network_links"]["linked"] == ["eno2"]
    assert impacts["pool_health"]["state"] == "ok"
    assert payload["pressure_state"] == "fail"
    assert CANARY not in json.dumps(payload)
    assert "<b>" not in json.dumps(payload)


def test_failing_methods_degrade_their_section_only() -> None:
    client = FakeClient(canned(), failures={"alert.list", "reporting.netdata_get_data"})
    payload = pulse.collect_appliance_pulse(FakeAdapter(client))

    assert payload["state"] == "partial"
    assert payload["alerts"]["state"] == "unavailable" and payload["alerts"]["active"] is None
    assert payload["cpu"]["state"] == "unavailable" and payload["cpu"]["series"] == []
    assert payload["storage"]["state"] == "observed"
    assert set(payload["errors"]) == {"alerts", "netdata"}
    assert all(value.endswith(":RuntimeError") for value in payload["errors"].values())
    assert CANARY not in json.dumps(payload)
    assert all(impact["id"] != "active_alerts" for impact in payload["impacts"])


def test_unrecognized_netdata_legend_is_reported_not_guessed() -> None:
    answers = canned()
    answers["reporting.netdata_get_data"] = [
        _netdata("cpu", ["time", "a", "b"], [[NOW, 1.0, 2.0], [NOW + 60, 1.0, 2.0]]),
        _netdata("memory", ["time", "x"], [[NOW, 1.0], [NOW + 60, 1.0]]),
        {"name": "interface", "identifier": "eno1", "legend": ["time", "received", "sent"], "data": [[NOW, 1.0, 1.0], [NOW - 5, 1.0, 1.0]]},
    ]
    payload = pulse.collect_appliance_pulse(FakeAdapter(FakeClient(answers)))

    assert payload["cpu"]["state"] == "legend_unrecognized" and payload["cpu"]["busy_percent"] is None
    assert payload["memory"]["state"] == "legend_unrecognized"
    assert payload["network"]["series"] == []  # non-monotonic timestamps rejected
    assert all(impact["id"] != "memory_pressure" for impact in payload["impacts"])


def test_dict_rows_and_out_of_range_percentages_are_handled() -> None:
    answers = canned()
    answers["reporting.netdata_get_data"] = [
        {"name": "cpu", "identifier": None, "legend": ["time", "idle"], "data": [{"time": NOW, "idle": 40.0}, {"time": NOW + 60, "idle": 250.0}]},
    ]
    payload = pulse.collect_appliance_pulse(FakeAdapter(FakeClient(answers)))
    assert payload["cpu"]["series"] == [[NOW, 60.0]]


@pytest.mark.asyncio
async def test_fetch_reports_not_configured_timeout_and_session_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pulse, "build_truenas_adapter", lambda: None)
    result = await pulse.fetch_appliance_pulse(use_cache=False)
    assert result["state"] == "not_configured" and result["synthetic"] is False

    failing = FakeAdapter(
        FakeClient({}),
        session_error=TrueNASHealthProbeError(phase="authentication", stage="auth_rejected", cause=RuntimeError(CANARY), method="auth.login_with_api_key", authenticated=False),
    )
    result = await pulse.fetch_appliance_pulse(adapter=failing, use_cache=False)
    assert result["state"] == "telemetry_unavailable" and result["reason"] == "auth_rejected"
    assert CANARY not in json.dumps(result)

    monkeypatch.setattr(pulse, "DEADLINE_SECONDS", 0.01)

    def slow(_adapter: Any) -> dict[str, Any]:
        time.sleep(0.2)
        return {}

    monkeypatch.setattr(pulse, "collect_appliance_pulse", slow)
    result = await pulse.fetch_appliance_pulse(adapter=FakeAdapter(FakeClient({})), use_cache=False)
    assert result["state"] == "telemetry_unavailable" and result["reason"] == "timeout"


@pytest.mark.asyncio
async def test_fetch_caches_for_thirty_seconds() -> None:
    client = FakeClient(canned())
    adapter = FakeAdapter(client)
    first = await pulse.fetch_appliance_pulse(adapter=adapter)
    second = await pulse.fetch_appliance_pulse(adapter=adapter)
    assert first["cached"] is False and second["cached"] is True
    assert len([m for m, _p in client.calls if m == "system.info"]) == 1
    assert second["model"] == "owner-appliance-pulse" and second["source"] == "truenas_middleware"
