"""Prometheus access boundaries must not silently turn redirects into empty metrics."""

from __future__ import annotations

import httpx
import pytest

from nabla.api.platform_metrics import fetch_platform_metrics
from nabla.settings.observability import HomelabPrometheusSettings


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected"),
    [(302, "access_redirect"), (401, "authentication_rejected"),
     (403, "authentication_rejected"), (429, "rate_limited"),
     (503, "http_failure")],
)
async def test_prometheus_http_problems_are_qualified(status: int, expected: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, request=request, headers={"Location": "/cdn-cgi/access"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://prometheus.test",
        follow_redirects=False,
    ) as client:
        value = await fetch_platform_metrics(
            settings=HomelabPrometheusSettings(homelab_prometheus_url="http://prometheus.test"),
            client=client,
        )
    assert value["state"] == "telemetry_unavailable"
    assert value["error_kind"] == expected
    assert value["http_status"] == status
    assert "Location" not in str(value)


@pytest.mark.asyncio
async def test_prometheus_html_response_is_invalid_not_no_metrics() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, text="<html>not prometheus</html>")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://prometheus.test",
    ) as client:
        value = await fetch_platform_metrics(
            settings=HomelabPrometheusSettings(homelab_prometheus_url="http://prometheus.test"),
            client=client,
        )
    assert value["error_kind"] == "invalid_response"
    assert value["state"] == "telemetry_unavailable"
