"""Budgeted aggregation of sampled homelab probe tasks."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Literal

from nabla.api.health_probe_utils import elapsed_ms
from nabla.api.homelab_models import HomelabService
from nabla.api.platform_health_diagnostics import short_error

ProbeScope = Literal["public", "internal"]

_TIMING_PHASES = (
    ("max_queue_wait_ms", "queue_wait_ms"),
    ("max_dns_probe_ms", "dns_probe_ms"),
    ("max_http_request_ms", "http_request_ms"),
    ("max_access_secondary_ms", "access_secondary_ms"),
)


def _probe_deadline_result(
    service: HomelabService,
    *,
    scope: ProbeScope,
) -> dict[str, Any]:
    """Represent unfinished fan-out without claiming the service is down."""
    result: dict[str, Any] = {
        "id": service.service_id,
        "name": service.name,
        "reachable": False,
        "state": "warn",
        "timed_out": True,
        "error_kind": "deadline",
        "error": "service probe fan-out budget exceeded",
    }
    if scope == "internal":
        result["host"] = service.internal_host
        result["port"] = service.internal_port
    else:
        result["url"] = service.public_https_probe_url
        result["http_status"] = 0
        result["tls_trusted"] = None
    return result


def _probe_exception_result(
    service: HomelabService,
    exc: BaseException,
    *,
    scope: ProbeScope,
) -> dict[str, Any]:
    """Convert an unexpected probe task failure into diagnostic data."""
    result = _probe_deadline_result(service, scope=scope)
    result.update(
        {
            "timed_out": False,
            "error_kind": "probe_error",
            "error": short_error(exc),
            "exception_type": type(exc).__name__,
        },
    )
    return result


def _timing_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize phase maxima of completed, instrumented probes only."""
    observed = [result["probe_timing"] for result in results if isinstance(result.get("probe_timing"), dict)]
    summary: dict[str, Any] = {"completed_samples": len(observed)}
    for key, phase in _TIMING_PHASES:
        values = [timing[phase] for timing in observed if isinstance(timing.get(phase), int)]
        summary[key] = max(values, default=None)
    return summary


async def collect_bounded_probe_batch(
    probes: list[tuple[HomelabService, asyncio.Task[dict[str, Any]]]],
    *,
    scope: ProbeScope,
    enabled: bool = True,
    eligible_count: int | None = None,
    per_probe_timeout_seconds: float,
    fanout_budget_seconds: float,
    max_concurrency: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Collect sampled fan-out without allowing it to consume core health."""
    started = time.perf_counter()
    eligible = len(probes) if eligible_count is None else eligible_count
    if not probes:
        return [], {
            "scope": scope,
            "enabled": enabled,
            "eligible": eligible,
            "sampled": 0,
            "scheduled": 0,
            "completed": 0,
            "timed_out": 0,
            "rotating_sample": eligible > 0,
            "budget_seconds": fanout_budget_seconds,
            "per_probe_timeout_seconds": per_probe_timeout_seconds,
            "max_concurrency": max_concurrency,
            "elapsed_ms": 0,
            "states": {"ok": 0, "warn": 0, "fail": 0},
        }

    tasks = [task for _, task in probes]
    done, pending = await asyncio.wait(
        tasks,
        timeout=fanout_budget_seconds,
    )

    results: list[dict[str, Any]] = []
    for service, task in probes:
        if task in done:
            try:
                results.append(task.result())
            except Exception as exc:
                results.append(
                    _probe_exception_result(service, exc, scope=scope),
                )
        else:
            results.append(_probe_deadline_result(service, scope=scope))

    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    states = {state: sum(result.get("state") == state for result in results) for state in ("ok", "warn", "fail")}
    return results, {
        "scope": scope,
        "enabled": enabled,
        "eligible": eligible,
        "sampled": len(probes),
        "scheduled": len(probes),
        "completed": len(done),
        "timed_out": len(pending),
        "rotating_sample": eligible > len(probes),
        "budget_seconds": fanout_budget_seconds,
        "per_probe_timeout_seconds": per_probe_timeout_seconds,
        "max_concurrency": max_concurrency,
        "elapsed_ms": elapsed_ms(started),
        "timing": _timing_summary(results),
        "states": states,
    }
