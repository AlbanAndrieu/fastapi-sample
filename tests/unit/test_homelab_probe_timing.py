"""Offline timing regressions for bounded public probes and Access enrichment."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from nabla.api import homelab_probe_batch, homelab_probe_runner
from nabla.api.homelab_models import HomelabService


def _public_service(service_id: str) -> HomelabService:
    return HomelabService(
        id=service_id,
        name=service_id,
        tunnelUrl=f"https://{service_id}.albandrieu.com",
        external=True,
    )


@pytest.mark.asyncio
async def test_public_probe_separates_queue_dns_and_http(monkeypatch) -> None:
    """Report phase durations without increasing concurrency or network I/O."""
    semaphore = asyncio.Semaphore(1)
    await semaphore.acquire()

    async def fake_dns(_host: str) -> dict[str, object]:
        await asyncio.sleep(0.008)
        return {"dns_reachable": True}

    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.008)
        return httpx.Response(
            405 if request.method == "HEAD" else 200,
            request=request,
        )

    monkeypatch.setattr(homelab_probe_runner, "probe_dns_hostname", fake_dns)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        task = asyncio.create_task(
            homelab_probe_runner.probe_http_endpoint(
                client,
                semaphore,
                service_id="garage-webui",
                name="Garage Web UI",
                url="https://garage.albandrieu.com",
            ),
        )
        await asyncio.sleep(0.025)
        semaphore.release()
        result = await task

    timing = result["probe_timing"]
    assert result["state"] == "ok"
    assert result["http_status"] == 200
    assert timing["queue_wait_ms"] >= 15
    assert timing["dns_probe_ms"] >= 1
    assert timing["http_request_ms"] >= 1
    assert timing["http_request_count"] == 2
    assert result["latency_ms"] >= timing["queue_wait_ms"]


@pytest.mark.asyncio
async def test_outside_in_probe_blocks_non_global_dns_without_http(monkeypatch) -> None:
    attempted: list[str] = []

    async def private_dns(_hostname: str) -> dict[str, object]:
        return {"dns_state": "ok", "dns_resolved": ["172.17.0.24"]}

    def handler(request: httpx.Request) -> httpx.Response:
        attempted.append(request.url.host or "")
        return httpx.Response(200, request=request)

    monkeypatch.setattr(homelab_probe_runner, "probe_dns_hostname", private_dns)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await homelab_probe_runner.probe_http_endpoint(
            client,
            asyncio.Semaphore(1),
            service_id="no-lan-target",
            name="Blocked private DNS",
            url="https://example.com",
        )
    assert attempted == []
    assert result["state"] == "warn"
    assert result["reachable"] is None
    assert result["probe_blocked"] is True
    assert result["error_kind"] == "non_global_dns_answer"
    assert result["probe_timing"]["http_request_count"] == 0


@pytest.mark.asyncio
async def test_failed_request_preserves_phase_evidence(monkeypatch) -> None:
    async def fake_dns(_host: str) -> dict[str, object]:
        return {}

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("synthetic TCP unavailable", request=request)

    monkeypatch.setattr(homelab_probe_runner, "probe_dns_hostname", fake_dns)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await homelab_probe_runner.probe_http_endpoint(
            client,
            asyncio.Semaphore(1),
            service_id="probe",
            name="Probe",
            url="https://probe.albandrieu.com",
        )

    assert result["state"] == "fail"
    assert result["http_status"] == 0
    assert result["probe_timing"]["http_request_count"] == 1
    assert result["probe_timing"]["http_request_ms"] is not None


@pytest.mark.asyncio
async def test_batch_timing_counts_only_observed_completed_results() -> None:
    observed, blocked = _public_service("observed"), _public_service("blocked")

    async def good() -> dict[str, object]:
        return {
            "id": observed.service_id,
            "state": "ok",
            "probe_timing": {
                "queue_wait_ms": 15,
                "dns_probe_ms": 8,
                "http_request_ms": 24,
                "access_secondary_ms": 11,
            },
        }

    async def pending() -> dict[str, object]:
        await asyncio.Event().wait()
        return {"id": blocked.service_id, "state": "ok"}

    results, summary = await homelab_probe_batch.collect_bounded_probe_batch(
        [
            (observed, asyncio.create_task(good())),
            (blocked, asyncio.create_task(pending())),
        ],
        scope="public",
        per_probe_timeout_seconds=3.0,
        fanout_budget_seconds=0.015,
        max_concurrency=4,
    )

    assert summary["completed"] == 1
    assert summary["timed_out"] == 1
    assert summary["timing"] == {
        "completed_samples": 1,
        "max_queue_wait_ms": 15,
        "max_dns_probe_ms": 8,
        "max_http_request_ms": 24,
        "max_access_secondary_ms": 11,
    }
    assert results[1]["state"] == "warn"
    assert results[1]["error_kind"] == "deadline"
    assert "probe_timing" not in results[1]


@pytest.mark.asyncio
async def test_access_secondary_latency_remains_distinct_from_http() -> None:
    service = HomelabService(
        id="garage-webui",
        name="Garage Web UI",
        external=True,
        tunnelUrl="https://garage.albandrieu.com",
        cloudflareAccessRequired=True,
    )

    async def http_probe(*_args, **_kwargs) -> dict[str, object]:
        return {
            "http_status": 302,
            "state": "ok",
            "probe_timing": {
                "queue_wait_ms": 0,
                "dns_probe_ms": 1,
                "http_request_ms": 2,
                "http_request_count": 1,
            },
        }

    async def edge_probe(_url: str) -> dict[str, object]:
        await asyncio.sleep(0.008)
        return {
            "cloudflare_access_signal": True,
            "cloudflare_default_deny": True,
        }

    async with httpx.AsyncClient() as client:
        result = await homelab_probe_runner.probe_public_service(
            client,
            asyncio.Semaphore(1),
            service,
            http_probe=http_probe,
            edge_probe=edge_probe,
        )

    assert result["cloudflare_access_secondary_probe_attempted"] is True
    assert result["probe_timing"]["access_secondary_ms"] >= 1
    assert result["probe_timing"]["http_request_ms"] == 2
    assert result["state"] == "warn"
    assert result["origin_reached"] is False
