"""Prometheus history is fixed-window, bounded, normalized and OWNER-only."""

from __future__ import annotations

import httpx
import pytest

from nabla.api import home_metrics_history as history
from nabla.settings.observability import HomelabPrometheusSettings

# Strict pytest-asyncio mode: every coroutine test in this module needs the marker.
pytestmark = pytest.mark.asyncio


def _settings() -> HomelabPrometheusSettings:
    return HomelabPrometheusSettings(
        homelab_prometheus_url="https://prometheus.albandrieu.com",
        homelab_prometheus_timeout_seconds=1.0,
    )


def _matrix(request: httpx.Request) -> httpx.Response:
    query = str(request.url.params["query"])
    end = int(request.url.params["end"])
    assert request.method == "GET"
    assert request.url.path == "/api/v1/query_range"
    assert request.url.params["step"] in {"60", "300", "1800"}
    assert "__name__" not in str(request.headers)
    if "container_cpu_usage" in query or "container_memory_working_set" in query or "container_network_receive" in query:
        assert 'container_label_com_docker_compose_service=~"' in query
        labels = {"container_label_com_docker_compose_service": "sample"}
    else:
        labels = {}
    return httpx.Response(
        200,
        request=request,
        json={
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {"metric": labels, "values": [[end - int(request.url.params["step"]), "0.25"], [end, "0.5"]]},
                ],
            },
        },
    )


@pytest.mark.parametrize(
    ("window", "step"),
    [("1h", 60), ("24h", 300), ("7d", 1800)],
)
async def test_fixed_history_only_queries_allowed_contract(window: str, step: int) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _matrix(request)

    async with httpx.AsyncClient(
        base_url="https://prometheus.albandrieu.com",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await history.fetch_home_metrics_history(
            window,
            settings=_settings(),
            client=client,
            enabled=True,
        )
    assert result["window"] == window
    assert result["step_seconds"] == step
    assert result["state"] == "observed"
    assert result["synthetic"] is False
    assert len(requests) == 5
    assert len(result["series"]["cpu_cores"]) == 2
    assert result["units"]["memory_bytes"] == "bytes"
    assert "container_label_com_docker_compose_service" not in str(result)
    assert "prometheus.albandrieu.com" not in str(result)
    assert all(str(request.url.params["query"]) in history._FIXED_QUERIES.values() for request in requests)


async def test_disabled_runtime_never_calls_prometheus() -> None:
    def fail(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("No external request allowed")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(fail),
        base_url="https://prometheus.albandrieu.com",
    ) as client:
        result = await history.fetch_home_metrics_history(
            "1h",
            settings=_settings(),
            client=client,
            enabled=False,
        )
    assert result["state"] == "not_executed"
    assert all(not points for points in result["series"].values())


async def test_unconfigured_has_no_history_or_false_zero() -> None:
    result = await history.fetch_home_metrics_history(
        "1h",
        settings=HomelabPrometheusSettings(homelab_prometheus_url=None),
        enabled=True,
    )
    assert result["state"] == "not_configured"
    assert result["series"]["cpu_cores"] == []


async def test_window_rejects_unbounded_input() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        await history.fetch_home_metrics_history("999d", enabled=True)


async def test_access_redirect_cannot_count_as_healthy_history() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            request=request,
            headers={"Location": "/cdn-cgi/access/login"},
        )

    async with httpx.AsyncClient(
        base_url="https://prometheus.albandrieu.com",
        follow_redirects=False,
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await history.fetch_home_metrics_history(
            "1h",
            settings=_settings(),
            client=client,
            enabled=True,
        )
    assert result["state"] == "telemetry_unavailable"
    assert all(kind == "access_redirect" for kind in result["errors"].values())
    assert "Location" not in str(result)


async def test_partial_telemetry_and_duplicate_series_are_unknown() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        response = _matrix(request)
        payload = response.json()
        query = str(request.url.params["query"])
        if "container_cpu_usage" in query:
            payload["data"]["result"].append(payload["data"]["result"][0])
        if "http_request_duration" in query:
            return httpx.Response(503, request=request)
        return httpx.Response(200, request=request, json=payload)

    async with httpx.AsyncClient(
        base_url="https://prometheus.albandrieu.com",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await history.fetch_home_metrics_history(
            "1h",
            settings=_settings(),
            client=client,
            enabled=True,
        )
    assert result["state"] == "partial"
    assert result["series"]["cpu_cores"] == []
    assert result["series"]["memory_bytes"]
    assert result["errors"]["http_p95_ms"] == "http_failure"


def test_matrix_filters_future_negative_nonfinite_and_out_of_range() -> None:
    spec = history._window("1h")
    observed = {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [
                {
                    "metric": {"container_label_com_docker_compose_service": "sample"},
                    "values": [
                        [spec.start - 100, "1"],
                        [spec.end - 60, "NaN"],
                        [spec.end - 10, "-2"],
                        [spec.end, "0"],
                        [spec.end + 700, "1"],
                    ],
                },
            ],
        },
    }
    assert history._sanitize_matrix(observed, "cpu_cores", spec) == [
        [spec.end, 0.0],
    ]
    assert (
        history._sanitize_matrix(
            {
                **observed,
                "data": {
                    "resultType": "matrix",
                    "result": [
                        {
                            "metric": {"container_label_com_docker_compose_service": "other"},
                            "values": [[spec.end, "99"]],
                        },
                    ],
                },
            },
            "cpu_cores",
            spec,
        )
        == []
    )


def test_matrix_rejects_oversized_or_invalid_contract() -> None:
    spec = history._window("7d")
    oversized = {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [
                {
                    "metric": {"container_label_com_docker_compose_service": "sample"},
                    "values": [[spec.end, "1"]] * 351,
                },
            ],
        },
    }
    with pytest.raises(ValueError, match="Oversized"):
        history._sanitize_matrix(oversized, "cpu_cores", spec)
    with pytest.raises(ValueError, match="matrix"):
        history._sanitize_matrix(
            {"status": "success", "data": {"resultType": "vector", "result": []}},
            "cpu_cores",
            spec,
        )
