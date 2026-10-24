"""Tests for the bounded homelab Prometheus aggregation contract."""

from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError

from nabla.api.platform_metrics import fetch_platform_metrics
from nabla.api.prometheus_query import safe_float, sample_value
from nabla.settings.observability import HomelabPrometheusSettings


def test_prometheus_numeric_samples_ignore_oversized_or_invalid_values() -> None:
    """Untrusted Prometheus payloads cannot crash the aggregation on huge ints."""
    huge = 10**1000
    assert safe_float(huge) is None
    assert sample_value({"value": [1, huge]}) is None
    assert safe_float(float("nan")) is None
    assert sample_value({"value": [1, "NaN"]}) is None
    assert safe_float("1.0") == 1.0


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
        query = request.url.params.get("query", "")
        assert " or " in query
        result = [
            {
                "metric": {"__name__": metric},
                "value": [1_700_000_000, value],
            }
            for metric, value in values.items()
            if value is not None and metric in query
        ]
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
        homelab_prometheus_url="http://prometheus.test",
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
        homelab_prometheus_url="http://prometheus.test",
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
        homelab_prometheus_url="http://prometheus.test",
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
            homelab_prometheus_url="http://user:password@prometheus.test",
        )


def test_prometheus_settings_reject_path() -> None:
    with pytest.raises(ValidationError):
        HomelabPrometheusSettings(
            homelab_prometheus_url="http://prometheus.test/prometheus",
        )


@pytest.mark.asyncio
async def test_platform_metrics_exposes_gatus_service_signals_as_shadow_only() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("query", "")
        assert "nabla:service:synthetic_probe_success" in query
        result = [
            {
                "metric": {"__name__": "nabla:telemetry:gatus_up"},
                "value": [1, "1"],
            },
            {
                "metric": {
                    "__name__": "nabla:service:synthetic_probe_success",
                    "nabla_service_id": "fastapi-sample",
                    "type": "HTTP",
                },
                "value": [1, "1"],
            },
            {
                "metric": {
                    "__name__": "nabla:service:synthetic_probe_duration_seconds",
                    "nabla_service_id": "fastapi-sample",
                    "type": "HTTP",
                },
                "value": [1, "0.125"],
            },
            {
                "metric": {
                    "__name__": "nabla:service:synthetic_availability_ratio_5m",
                    "nabla_service_id": "fastapi-sample",
                    "type": "HTTP",
                },
                "value": [1, "0.99"],
            },
            {
                "metric": {
                    "__name__": "nabla:service:synthetic_probe_success",
                    "nabla_service_id": "vaultwarden",
                    "type": "TCP",
                },
                "value": [1, "1"],
            },
        ]
        return httpx.Response(
            200,
            request=request,
            json={
                "status": "success",
                "data": {"resultType": "vector", "result": result},
            },
        )

    settings = HomelabPrometheusSettings(
        homelab_prometheus_url="http://prometheus.test",
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://prometheus.test",
    ) as client:
        payload = await fetch_platform_metrics(
            settings=settings,
            client=client,
        )

    synthetic = payload["synthetic_probes"]
    assert synthetic["shadow_only"] is True
    assert synthetic["state"] == "observed"
    assert synthetic["service_count"] == 2
    assert synthetic["services"]["fastapi-sample"]["HTTP"] == {
        "success": 1.0,
        "duration_seconds": 0.125,
        "availability_ratio_5m": 0.99,
    }
    assert synthetic["services"]["vaultwarden"]["TCP"] == {"success": 1.0}


@pytest.mark.asyncio
async def test_gatus_raw_up_is_bounded_fallback_without_faking_monitor_coverage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("query", "")
        assert 'up{job="gatus"}' in query
        return httpx.Response(
            200,
            request=request,
            json={
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {
                            "metric": {"__name__": "up", "job": "gatus"},
                            "value": [1, "1"],
                        },
                    ],
                },
            },
        )

    settings = HomelabPrometheusSettings(
        homelab_prometheus_url="http://prometheus.test",
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://prometheus.test",
    ) as client:
        payload = await fetch_platform_metrics(settings=settings, client=client)
    synthetic = payload["synthetic_probes"]
    assert synthetic["gatus_up"] == 1.0
    assert synthetic["gatus_source"] == "raw_prometheus_up"
    assert synthetic["service_count"] == 0
    assert synthetic["services"] == {}


@pytest.mark.asyncio
async def test_gatus_recording_rule_takes_priority_over_raw_up() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {"metric": {"__name__": "up", "job": "gatus"}, "value": [1, "1"]},
                        {"metric": {"__name__": "nabla:telemetry:gatus_up"}, "value": [1, "0"]},
                    ],
                },
            },
        )

    settings = HomelabPrometheusSettings(
        homelab_prometheus_url="http://prometheus.test",
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://prometheus.test",
    ) as client:
        payload = await fetch_platform_metrics(settings=settings, client=client)
    assert payload["synthetic_probes"]["gatus_up"] == 0.0
    assert payload["synthetic_probes"]["gatus_source"] == "recording_rule"


@pytest.mark.asyncio
async def test_optional_exporters_are_visible_without_changing_required_gate() -> None:
    values = dict(VALUES)
    values.update(
        {
            "nabla:telemetry:postgres_exporter_up": "1",
            "nabla:telemetry:redis_exporter_up": "0",
            "nabla:telemetry:fastapi_sample_up": "1",
            "nabla:telemetry:pyroscope_up": "0",
            "nabla:telemetry:alertmanager_up": "1",
            "nabla:service:postgres_up": "1",
            "nabla:service:redis_up": "0",
            "nabla:core:pfsense_memory_available_ratio": "0.68",
        },
    )
    settings = HomelabPrometheusSettings(homelab_prometheus_url="http://prometheus.test")
    async with _client(values) as client:
        payload = await fetch_platform_metrics(settings=settings, client=client)

    assert payload["state"] == "healthy"
    assert payload["summary"]["signals_total"] == 6
    assert payload["summary"]["optional_exporters"] == {
        "postgres_exporter_up": 1.0,
        "redis_exporter_up": 0.0,
        "fastapi_sample_up": 1.0,
        "pyroscope_up": 0.0,
        "alertmanager_up": 1.0,
        "postgres_up": 1.0,
        "redis_up": 0.0,
        "pfsense_memory_available_ratio": 0.68,
    }


@pytest.mark.asyncio
async def test_missing_optional_exporters_are_unknown_not_platform_outage() -> None:
    settings = HomelabPrometheusSettings(homelab_prometheus_url="http://prometheus.test")
    async with _client(VALUES) as client:
        payload = await fetch_platform_metrics(settings=settings, client=client)
    assert payload["state"] == "healthy"
    assert all(value is None for value in payload["summary"]["optional_exporters"].values())


@pytest.mark.asyncio
async def test_exporter_job_inventory_is_bounded_and_does_not_change_health() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        samples = [{"metric": {"__name__": name}, "value": [1, value]} for name, value in VALUES.items()]
        for job, value in (
            ("kafka_exporter", "1"),
            ("opensearch", "0"),
            ("cloudflare_exporter", "1"),
            ("unexpected_job", "1"),
        ):
            samples.append(
                {
                    "metric": {"__name__": "nabla:telemetry:service_exporter_up", "job": job},
                    "value": [1, value],
                },
            )
        return httpx.Response(
            200,
            request=request,
            json={"status": "success", "data": {"resultType": "vector", "result": samples}},
        )

    settings = HomelabPrometheusSettings(
        homelab_prometheus_url="http://prometheus.test",
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://prometheus.test",
    ) as client:
        payload = await fetch_platform_metrics(settings=settings, client=client)

    assert payload["state"] == "healthy"
    assert payload["exporter_jobs"] == {
        "kafka_exporter": 1.0,
        "opensearch": 0.0,
        "cloudflare_exporter": 1.0,
    }
    assert "unexpected_job" not in payload["exporter_jobs"]
    assert payload["summary"]["signals_total"] == 6


@pytest.mark.asyncio
async def test_conflicting_exporter_samples_fail_closed_independent_of_order() -> None:
    for samples in (("1", "0"), ("0", "1")):

        def handler(
            request: httpx.Request,
            samples: tuple[str, str] = samples,
        ) -> httpx.Response:
            result = [{"metric": {"__name__": name}, "value": [1, value]} for name, value in VALUES.items()]
            result.extend(
                {
                    "metric": {
                        "__name__": "nabla:telemetry:service_exporter_up",
                        "job": "redis_exporter",
                    },
                    "value": [1, value],
                }
                for value in samples
            )
            return httpx.Response(
                200,
                request=request,
                json={"status": "success", "data": {"resultType": "vector", "result": result}},
            )

        settings = HomelabPrometheusSettings(
            homelab_prometheus_url="http://prometheus.test",
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://prometheus.test",
        ) as client:
            payload = await fetch_platform_metrics(settings=settings, client=client)
        assert payload["exporter_jobs"]["redis_exporter"] == 0.0
        assert payload["state"] == "healthy"


@pytest.mark.asyncio
async def test_gatus_samples_are_bounded_and_conflicts_fail_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        samples = [{"metric": {"__name__": name}, "value": [1, value]} for name, value in VALUES.items()]
        for metric, labels, value in (
            ("nabla:telemetry:gatus_up", {}, "1"),
            ("nabla:telemetry:gatus_up", {}, "0"),
            ("nabla:service:synthetic_probe_success", {"nabla_service_id": "nexus", "type": "TCP"}, "1"),
            ("nabla:service:synthetic_probe_success", {"nabla_service_id": "nexus", "type": "TCP"}, "0"),
            ("nabla:service:synthetic_probe_success", {"nabla_service_id": "nexus", "type": "TCP"}, "2"),
            ("nabla:service:synthetic_probe_duration_seconds", {"nabla_service_id": "nexus", "type": "TCP"}, "-1"),
            ("nabla:service:synthetic_probe_duration_seconds", {"nabla_service_id": "nexus", "type": "TCP"}, "0.2"),
            ("nabla:service:synthetic_probe_duration_seconds", {"nabla_service_id": "nexus", "type": "TCP"}, "0.3"),
            ("nabla:service:synthetic_probe_success", {"nabla_service_id": "nexus", "type": "UNKNOWN"}, "1"),
        ):
            samples.append({"metric": {"__name__": metric, **labels}, "value": [1, value]})
        return httpx.Response(
            200,
            request=request,
            json={
                "status": "success",
                "data": {"resultType": "vector", "result": samples},
            },
        )

    settings = HomelabPrometheusSettings(homelab_prometheus_url="http://prometheus.test")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://prometheus.test",
    ) as client:
        payload = await fetch_platform_metrics(settings=settings, client=client)

    assert payload["synthetic_probes"]["gatus_up"] == 0.0
    assert payload["synthetic_probes"]["state"] == "telemetry_unavailable"
    assert payload["synthetic_probes"]["services"]["nexus"] == {
        "TCP": {"success": 0.0, "duration_seconds": 0.3},
    }


@pytest.mark.asyncio
async def test_gatus_service_identifiers_reject_invalid_and_oversized_labels() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        rows = [
            {
                "metric": {
                    "__name__": "nabla:service:synthetic_probe_success",
                    "nabla_service_id": sid,
                    "type": "HTTP",
                },
                "value": [1, "1"],
            }
            for sid in ("valid-service", "CAPITALIZED", "../secret", "a" * 81, " bad ", "")
        ]
        return httpx.Response(
            200,
            request=request,
            json={"status": "success", "data": {"resultType": "vector", "result": rows}},
        )

    settings = HomelabPrometheusSettings(homelab_prometheus_url="http://prometheus.test")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://prometheus.test",
    ) as client:
        result = await fetch_platform_metrics(settings=settings, client=client)
    assert set(result["synthetic_probes"]["services"]) == {"valid-service"}


@pytest.mark.asyncio
async def test_gatus_service_series_count_is_bounded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        rows = [
            {
                "metric": {
                    "__name__": "nabla:service:synthetic_probe_success",
                    "nabla_service_id": f"service-{index}",
                    "type": "TCP",
                },
                "value": [1, "1"],
            }
            for index in range(350)
        ]
        return httpx.Response(
            200,
            request=request,
            json={"status": "success", "data": {"resultType": "vector", "result": rows}},
        )

    settings = HomelabPrometheusSettings(homelab_prometheus_url="http://prometheus.test")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://prometheus.test",
    ) as client:
        result = await fetch_platform_metrics(settings=settings, client=client)
    assert result["synthetic_probes"]["service_count"] == 256
    assert result["synthetic_probes"]["truncated"] is True
    assert result["synthetic_probes"]["state"] == "telemetry_unavailable"


@pytest.mark.asyncio
async def test_gatus_raw_up_conflicting_series_are_order_independent() -> None:
    for pair in (("1", "0"), ("0", "1")):

        def handler(
            request: httpx.Request,
            pair: tuple[str, str] = pair,
        ) -> httpx.Response:
            samples = [
                {
                    "metric": {"__name__": "up", "job": "gatus", "instance": str(index)},
                    "value": [1, status],
                }
                for index, status in enumerate(pair)
            ]
            return httpx.Response(
                200,
                request=request,
                json={"status": "success", "data": {"resultType": "vector", "result": samples}},
            )

        settings = HomelabPrometheusSettings(
            homelab_prometheus_url="http://prometheus.test",
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://prometheus.test",
        ) as client:
            payload = await fetch_platform_metrics(settings=settings, client=client)
        assert payload["synthetic_probes"]["gatus_up"] == 0.0
        assert payload["synthetic_probes"]["gatus_source"] == "raw_prometheus_up"
        assert payload["synthetic_probes"]["state"] == "telemetry_unavailable"


@pytest.mark.asyncio
async def test_akvorado_scrape_jobs_use_fixed_bounded_raw_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]
        assert 'up{job=~"akvorado_inlet|akvorado_outlet"}' in query
        rows = [
            {
                "metric": {"__name__": "up", "job": job},
                "value": [1, value],
            }
            for job, value in (
                ("akvorado_inlet", "1"),
                ("akvorado_outlet", "0"),
                ("not_approved", "1"),
            )
        ]
        return httpx.Response(
            200,
            request=request,
            json={
                "status": "success",
                "data": {"resultType": "vector", "result": rows},
            },
        )

    settings = HomelabPrometheusSettings(
        homelab_prometheus_url="http://prometheus.test"
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://prometheus.test",
    ) as client:
        result = await fetch_platform_metrics(settings=settings, client=client)

    assert result["exporter_jobs"] == {
        "akvorado_inlet": 1.0,
        "akvorado_outlet": 0.0,
    }
    assert result["state"] == "degraded"


@pytest.mark.asyncio
async def test_akvorado_recorded_and_raw_conflicts_fail_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        rows = [
            {
                "metric": {"__name__": "nabla:telemetry:service_exporter_up",
                           "job": "akvorado_inlet"},
                "value": [1, "1"],
            },
            {
                "metric": {"__name__": "up", "job": "akvorado_inlet"},
                "value": [1, "0"],
            },
        ]
        return httpx.Response(
            200,
            request=request,
            json={"status": "success", "data": {
                "resultType": "vector", "result": rows,
            }},
        )

    settings = HomelabPrometheusSettings(
        homelab_prometheus_url="http://prometheus.test"
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://prometheus.test",
    ) as client:
        result = await fetch_platform_metrics(settings=settings, client=client)
    assert result["exporter_jobs"]["akvorado_inlet"] == 0.0
    assert "akvorado_outlet" not in result["exporter_jobs"]
