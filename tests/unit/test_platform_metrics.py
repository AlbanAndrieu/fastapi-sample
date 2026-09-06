"""Tests for the bounded homelab Prometheus aggregation contract."""

from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError

from nabla.api.platform_metrics import fetch_platform_metrics
from nabla.settings.observability import HomelabPrometheusSettings


VALUES = {
    "nabla:core:truenas_memory_available_ratio": "0.42",
    "nabla:core:truenas_cpu_busy_ratio": "0.18",
    "nabla:telemetry:truenas_node_up": "1",
    "nabla:telemetry:truenas_cadvisor_up": "1",
    "nabla:telemetry:pfsense_metrics_up": "1",
    "nabla:observability:prometheus_up": "1",
}


def _client(values: dict[str, str | None]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        metric = request.url.params.get("query", "")
        value = values.get(metric)
        result = (
            []
            if value is None
            else [
                {
                    "metric": {"__name__": metric},
                    "value": [1_700_000_000, value],
                }
            ]
        )
        return httpx.Response(
            200,
            request=request,
            json={
                "status": "success",
                "data": {"resultType": "vector", "result": result},
            },
        )

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://prometheus.test",
    )


@pytest.mark.asyncio
async def test_platform_metrics_reads_only_fixed_recording_rules() -> None:
    settings = HomelabPrometheusSettings(
        homelab_prometheus_url="http://prometheus.test"
    )
    async with _client(VALUES) as client:
        payload = await fetch_platform_metrics(settings=settings, client=client)

    assert payload["state"] == "healthy"
    assert payload["configured"] is True
    assert payload["summary"]["telemetry_up"] == 4
    assert payload["summary"]["telemetry_total"] == 4
    assert payload["summary"]["truenas_memory_available_ratio"] == 0.42
    assert payload["summary"]["truenas_cpu_busy_ratio"] == 0.18
    assert payload["summary"]["pfsense_metrics_up"] == 1.0
    assert set(payload["metrics"]) == {
        "truenas_memory_available_ratio",
        "truenas_cpu_busy_ratio",
        "truenas_node_up",
        "truenas_cadvisor_up",
        "pfsense_metrics_up",
        "prometheus_up",
    }


@pytest.mark.asyncio
async def test_platform_metrics_missing_signal_is_degraded_not_platform_down() -> None:
    values = dict(VALUES)
    values["nabla:telemetry:truenas_cadvisor_up"] = None
    settings = HomelabPrometheusSettings(
        homelab_prometheus_url="http://prometheus.test"
    )
    async with _client(values) as client:
        payload = await fetch_platform_metrics(settings=settings, client=client)

    assert payload["state"] == "degraded"
    assert payload["summary"]["signals_available"] == 5
    assert payload["summary"]["telemetry_up"] == 3


@pytest.mark.asyncio
async def test_platform_metrics_not_configured_is_explicit() -> None:
    payload = await fetch_platform_metrics(settings=HomelabPrometheusSettings())

    assert payload["state"] == "not_configured"
    assert payload["configured"] is False
    assert payload["metrics"] == {}


@pytest.mark.asyncio
async def test_platform_metrics_transport_failure_is_sanitized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret internal route", request=request)

    settings = HomelabPrometheusSettings(
        homelab_prometheus_url="http://prometheus.test"
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://prometheus.test",
    ) as client:
        payload = await fetch_platform_metrics(settings=settings, client=client)

    assert payload["state"] == "telemetry_unavailable"
    assert payload["error_kind"] == "query_failed"
    assert payload["exception_type"] == "ConnectError"
    assert "secret" not in str(payload)


def test_prometheus_settings_reject_embedded_credentials() -> None:
    with pytest.raises(ValidationError):
        HomelabPrometheusSettings(
            homelab_prometheus_url="http://user:password@prometheus.test"
        )
