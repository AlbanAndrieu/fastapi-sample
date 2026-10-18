"""Offline contracts for bounded public probe cancellation phase attribution."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from nabla.api import (
    homelab_probe_batch,
    homelab_probe_runner,
)
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_probe_evidence import merge_probe_evidence, reset_probe_evidence
from nabla.api.homelab_probe_phase_tracker import (
    DEADLINE_PHASES,
    clear_probe_phase,
    mark_probe_phase,
    snapshot_probe_phase,
)


def _service(identifier: str) -> HomelabService:
    return HomelabService(
        id=identifier,
        name=identifier,
        tunnelUrl=f"https://{identifier}.example.com",
        external=True,
    )


@pytest.mark.asyncio
async def test_budget_captures_all_fixed_phases_before_cancellation() -> None:
    blockers = [asyncio.Event() for _ in DEADLINE_PHASES]

    async def blocked(phase: str | None, release: asyncio.Event) -> dict:
        if phase is not None:
            mark_probe_phase(phase)
        await release.wait()
        return {"state": "ok"}

    probes = [
        (
            _service(f"probe-{index}"),
            asyncio.create_task(
                blocked(None if phase == "not_started" else phase, blockers[index]),
            ),
        )
        for index, phase in enumerate(DEADLINE_PHASES)
    ]
    rows, summary = await homelab_probe_batch.collect_bounded_probe_batch(
        probes,
        scope="public",
        per_probe_timeout_seconds=3.0,
        fanout_budget_seconds=0.02,
        max_concurrency=4,
    )
    assert summary["timed_out"] == len(DEADLINE_PHASES)
    assert summary["completed"] == 0
    assert summary["deadline_phase_counts"] == dict.fromkeys(DEADLINE_PHASES, 1)
    assert [row["deadline_phase"] for row in rows] == list(DEADLINE_PHASES)
    assert all(row["state"] == "warn" for row in rows)
    assert all(row["error_kind"] == "deadline" for row in rows)
    assert all(row["reachable"] is False for row in rows)
    assert rows[0]["deadline_phase_elapsed_ms"] is None
    assert all(
        type(row["deadline_phase_elapsed_ms"]) is int
        for row in rows[1:]
    )
    # The fixed tracker does not retain a cancelled task after the batch.
    for _, task in probes:
        assert task.cancelled()
        assert snapshot_probe_phase(task)["deadline_phase"] == "not_started"


@pytest.mark.asyncio
async def test_runner_marks_queue_dns_http_and_access_without_real_network(
    monkeypatch,
) -> None:
    gate = asyncio.Event()
    semaphore = asyncio.Semaphore(1)
    await semaphore.acquire()

    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, request=request),
    )) as client:
        queued = asyncio.create_task(homelab_probe_runner.probe_http_endpoint(
            client,
            semaphore,
            service_id="queued",
            name="Queued",
            url="https://queued.example.com",
        ))
        await asyncio.sleep(0.01)
        assert snapshot_probe_phase(queued)["deadline_phase"] == "waiting_on_semaphore"
        queued.cancel()
        await asyncio.gather(queued, return_exceptions=True)
        clear_probe_phase(queued)

        dns_entered = asyncio.Event()

        async def slow_dns(_hostname: str) -> dict:
            dns_entered.set()
            await gate.wait()
            return {}

        monkeypatch.setattr(homelab_probe_runner, "probe_dns_hostname", slow_dns)
        dns = asyncio.create_task(homelab_probe_runner.probe_http_endpoint(
            client,
            asyncio.Semaphore(1),
            service_id="dns",
            name="DNS",
            url="https://dns.example.com",
        ))
        await asyncio.wait_for(dns_entered.wait(), timeout=1)
        assert snapshot_probe_phase(dns)["deadline_phase"] == "dns_in_progress"
        dns.cancel()
        await asyncio.gather(dns, return_exceptions=True)
        clear_probe_phase(dns)

        async def fast_dns(_hostname: str) -> dict:
            return {}

        entered_http = asyncio.Event()

        async def slow_http(request: httpx.Request) -> httpx.Response:
            entered_http.set()
            await gate.wait()
            return httpx.Response(200, request=request)

        monkeypatch.setattr(homelab_probe_runner, "probe_dns_hostname", fast_dns)
        async with httpx.AsyncClient(transport=httpx.MockTransport(slow_http)) as blocked_client:
            http_task = asyncio.create_task(homelab_probe_runner.probe_http_endpoint(
                blocked_client,
                asyncio.Semaphore(1),
                service_id="http",
                name="HTTP",
                url="https://http.example.com",
            ))
            await asyncio.wait_for(entered_http.wait(), timeout=1)
            assert snapshot_probe_phase(http_task)["deadline_phase"] == "head_get_in_progress"
            http_task.cancel()
            await asyncio.gather(http_task, return_exceptions=True)
            clear_probe_phase(http_task)

        entered_edge = asyncio.Event()

        async def fake_probe(*_args, **_kwargs) -> dict:
            return {"http_status": 302, "state": "ok", "probe_timing": {}}

        async def slow_edge(_url: str) -> dict:
            entered_edge.set()
            await gate.wait()
            return {}

        edge_task = asyncio.create_task(homelab_probe_runner.probe_public_service(
            client,
            asyncio.Semaphore(1),
            HomelabService(
                id="edge",
                name="Edge",
                external=True,
                tunnelUrl="https://edge.example.com",
                cloudflareAccessRequired=True,
            ),
            http_probe=fake_probe,
            edge_probe=slow_edge,
        ))
        await asyncio.wait_for(entered_edge.wait(), timeout=1)
        assert snapshot_probe_phase(edge_task)["deadline_phase"] == "access_secondary_in_progress"
        edge_task.cancel()
        await asyncio.gather(edge_task, return_exceptions=True)
        clear_probe_phase(edge_task)
    semaphore.release()


@pytest.mark.asyncio
async def test_last_failed_attempt_does_not_replace_retained_healthy_evidence() -> None:
    reset_probe_evidence()
    service = _service("retained")
    successful = merge_probe_evidence(
        "public",
        current_results=[
            {"id": service.service_id, "state": "ok", "reachable": True, "http_status": 200},
        ],
        eligible_services=[service],
        checked_at="2026-10-17T22:00:00Z",
        now=1000.0,
    )
    assert successful[0]["probe_source"] == "origin"

    retained = merge_probe_evidence(
        "public",
        current_results=[
            {
                "id": service.service_id,
                "state": "warn",
                "timed_out": True,
                "error": "service probe fan-out budget exceeded",
                "deadline_phase": "dns_in_progress",
                "deadline_phase_elapsed_ms": 1042,
            },
        ],
        eligible_services=[service],
        checked_at="2026-10-17T22:00:30Z",
        now=1030.0,
    )
    assert retained[0]["probe_source"] == "memory"
    assert retained[0]["state"] == "ok"
    assert retained[0]["reachable"] is True
    assert retained[0]["http_status"] == 200
    assert retained[0]["last_probe_attempt_deadline_phase"] == "dns_in_progress"
    assert retained[0]["last_probe_attempt_deadline_phase_elapsed_ms"] == 1042
    reset_probe_evidence()


@pytest.mark.asyncio
async def test_tracker_rejects_arbitrary_phase_labels() -> None:
    with pytest.raises(ValueError, match="unrecognized probe phase"):
        mark_probe_phase("Bearer NEVER_LEAK")  # type: ignore[arg-type]
    assert all("NEVER_LEAK" not in phase for phase in DEADLINE_PHASES)


@pytest.mark.asyncio
async def test_pre_cancelled_child_is_warning_not_batch_failure() -> None:
    """Child cancellation must not propagate through the health collector."""

    async def pending() -> dict:
        await asyncio.Event().wait()
        return {"state": "ok"}

    task = asyncio.create_task(pending())
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    rows, summary = await homelab_probe_batch.collect_bounded_probe_batch(
        [(_service("cancelled"), task)],
        scope="public",
        per_probe_timeout_seconds=1.0,
        fanout_budget_seconds=0.02,
        max_concurrency=1,
    )
    assert summary["scheduled"] == 1
    assert summary["completed"] == 0
    assert summary["cancelled"] == 1
    assert summary["timed_out"] == 0
    assert summary["states"]["warn"] == 1
    assert summary["deadline_phase_counts"] == dict.fromkeys(DEADLINE_PHASES, 0)
    assert rows[0]["state"] == "warn"
    assert rows[0]["error_kind"] == "probe_cancelled"
    assert rows[0]["timed_out"] is False
    assert rows[0]["reachable"] is False
