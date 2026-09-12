"""Tests for bounded topology resource/flow telemetry."""

from __future__ import annotations

import httpx
import pytest

from nabla.api.topology_telemetry import (
    _flow_values,
    _resource_values,
    fetch_topology_telemetry,
)
from nabla.settings.observability import HomelabPrometheusSettings


def _sample(name: str, value: str, **labels: str) -> dict[str, object]:
    return {
        "metric": {"__name__": name, **labels},
        "value": [1_700_000_000, value],
    }


def test_resource_values_join_cadvisor_dimensions_by_compose_service() -> None:
    label = "container_label_com_docker_compose_service"
    result = _resource_values(
        {
            "cpu_cores": [_sample("cpu", "0.25", **{label: "fastapi-sample"})],
            "memory_bytes": [_sample("memory", "104857600", **{label: "fastapi-sample"})],
            "rx_bytes_per_second": [_sample("rx", "1200", **{label: "fastapi-sample"})],
            "tx_bytes_per_second": [_sample("tx", "800", **{label: "fastapi-sample"})],
        }
    )

    assert result["fastapi-sample"]["cpu_cores"] == 0.25
    assert result["fastapi-sample"]["memory_bytes"] == 104857600.0
    assert result["fastapi-sample"]["network_bytes_per_second"] == 2000.0


def test_flow_values_keep_akvorado_pipeline_evidence_separate_from_edges() -> None:
    result = _flow_values(
        [
            _sample("nabla:network_flow:pfsense_bytes_per_second", "4096"),
            _sample("nabla:network_flow:pfsense_packets_per_second", "32"),
            _sample("nabla:telemetry:akvorado_inlet_up", "1"),
            _sample("nabla:telemetry:akvorado_outlet_up", "1"),
        ]
    )

    assert result["pfsense_bytes_per_second"] == 4096.0
    assert result["pfsense_packets_per_second"] == 32.0
    assert result["akvorado_inlet_up"] == 1.0
    assert result["akvorado_outlet_up"] == 1.0


@pytest.mark.asyncio
async def test_topology_telemetry_is_safe_when_prometheus_is_not_configured() -> None:
    settings = HomelabPrometheusSettings(homelab_prometheus_url="")

    result = await fetch_topology_telemetry(settings=settings)

    assert result["state"] == "not_configured"
    assert result["configured"] is False
    assert result["resources"] == {}
    assert result["edge_bandwidth"] == {}
    assert result["edge_bandwidth_state"] == "unavailable"


@pytest.mark.asyncio
async def test_topology_telemetry_queries_prometheus_without_inventing_edge_bandwidth() -> None:
    label = "container_label_com_docker_compose_service"

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("query", "")
        if "container_cpu_usage_seconds_total" in query:
            result = [_sample("", "0.4", **{label: "fastapi-sample"})]
        elif "container_memory_working_set_bytes" in query:
            result = [_sample("", "209715200", **{label: "fastapi-sample"})]
        elif "container_network_receive_bytes_total" in query:
            result = [_sample("", "2048", **{label: "fastapi-sample"})]
        elif "container_network_transmit_bytes_total" in query:
            result = [_sample("", "1024", **{label: "fastapi-sample"})]
        else:
            result = [
                _sample("nabla:network_flow:pfsense_bytes_per_second", "8192"),
                _sample("nabla:telemetry:akvorado_inlet_up", "1"),
                _sample("nabla:telemetry:akvorado_outlet_up", "1"),
            ]
        return httpx.Response(
            200,
            json={"status": "success", "data": {"resultType": "vector", "result": result}},
        )

    client = httpx.AsyncClient(
        base_url="http://prometheus.test",
        transport=httpx.MockTransport(handler),
    )
    settings = HomelabPrometheusSettings(
        homelab_prometheus_url="http://prometheus.test"
    )
    try:
        result = await fetch_topology_telemetry(settings=settings, client=client)
    finally:
        await client.aclose()

    assert result["state"] == "healthy"
    assert result["resources"]["fastapi-sample"]["cpu_cores"] == 0.4
    assert result["resources"]["fastapi-sample"]["network_bytes_per_second"] == 3072.0
    assert result["network_flow"]["pfsense_bytes_per_second"] == 8192.0
    assert result["edge_bandwidth"] == {}
    assert result["edge_bandwidth_state"] == "unattributed"
