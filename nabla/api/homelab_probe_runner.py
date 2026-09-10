"""Bounded HTTP/HTTPS/TCP probe primitives for homelab health."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Literal

import httpx

from nabla.api.health_probe_utils import is_textual_response, looks_like_tls_error
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_probe_policy import (
    INTERNAL_PROBE_TIMEOUT_SEC as _INTERNAL_PROBE_TIMEOUT_SEC,
    MAX_PROBE_CONCURRENCY as _MAX_PROBE_CONCURRENCY,
    SERVICE_FANOUT_BUDGET_SEC as _SERVICE_FANOUT_BUDGET_SEC,
)
from nabla.api.sickz_cloudflare_edge import _probe_http_edge_evidence
from nabla.utils.environment import env_bool

HealthState = Literal["ok", "warn", "fail"]
_WARNING_HTTP_STATUSES = frozenset({401, 403, 407, 429})
_PROBE_TIMEOUT_SEC = 5.0
_INTERNAL_PROBE_ENV = "HOMELAB_INTERNAL_PROBES_ENABLED"
_MAX_APPLICATION_BODY_BYTES = 16_384
_APPLICATION_ERROR_PREFIXES = (
    "error:",
    "fatal:",
    "exception:",
    "application error",
    "internal server error",
    "bad gateway",
    "service unavailable",
)
_APPLICATION_ERROR_MARKERS = (
    "traceback (most recent call last)",
    "uncaught exception",
    "unhandled exception",
)


def classify_public_http_status(status: int) -> HealthState:
    """Map an endpoint HTTP status to service health semantics."""
    if 200 <= status <= 399:
        return "ok"
    if status in _WARNING_HTTP_STATUSES:
        return "warn"
    return "fail"


def internal_probes_enabled() -> bool:
    return env_bool(_INTERNAL_PROBE_ENV)


def _short_error(exc: BaseException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:240]


def _application_error_from_response(response: httpx.Response) -> str | None:
    if not (200 <= response.status_code <= 299) or not is_textual_response(response):
        return None
    content_type = response.headers.get("content-type", "").lower()
    if "json" in content_type:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            value = (
                payload.get("error")
                or payload.get("errors")
                or payload.get("exception")
            )
            if value:
                message = re.sub(r"\s+", " ", str(value)).strip()
                return message[:240] or "Application error"

    text = response.text[:_MAX_APPLICATION_BODY_BYTES].strip()
    if not text:
        return None
    lowered_raw = text.casefold()
    plain = re.sub(r"<[^>]+>", " ", text)
    plain = re.sub(r"\s+", " ", plain).strip()
    lowered_plain = plain.casefold()
    if any(lowered_plain.startswith(prefix) for prefix in _APPLICATION_ERROR_PREFIXES):
        return plain[:240]
    if any(marker in lowered_raw for marker in _APPLICATION_ERROR_MARKERS):
        return plain[:240]
    if re.search(
        r"<(?:title|h1)[^>]*>\s*(?:error|fatal|exception|application error|internal server error|bad gateway|service unavailable)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return plain[:240]
    return None


async def _probe_http_endpoint(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    *,
    service_id: str,
    name: str,
    url: str,
) -> dict[str, Any]:
    """Probe HTTP(S) and preserve transport, TLS and application evidence."""
    started = time.perf_counter()
    try:
        async with semaphore:
            response = await client.head(
                url,
                headers={"User-Agent": "nabla-homelab-health/1.0"},
            )
            should_get = response.status_code in {405, 501} or (
                200 <= response.status_code <= 299 and is_textual_response(response)
            )
            if should_get:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "nabla-homelab-health/1.0",
                        "Range": f"bytes=0-{_MAX_APPLICATION_BODY_BYTES - 1}",
                        "Accept": "text/html,text/plain,application/json,*/*;q=0.1",
                    },
                )
        status = response.status_code
        application_error = _application_error_from_response(response)
        result: dict[str, Any] = {
            "id": service_id,
            "name": name,
            "url": url,
            "reachable": True,
            "http_status": status,
            "state": (
                "fail" if application_error else classify_public_http_status(status)
            ),
            "tls_trusted": True,
        }
        if application_error:
            result["application_error"] = application_error
    except (httpx.HTTPError, OSError) as exc:
        error = _short_error(exc)
        result = {
            "id": service_id,
            "name": name,
            "url": url,
            "reachable": False,
            "http_status": 0,
            "state": "fail",
            "tls_trusted": False if looks_like_tls_error(error) else None,
            "error": error,
        }
    result["latency_ms"] = max(0, round((time.perf_counter() - started) * 1000))
    return result


async def _probe_public_service(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    service: HomelabService,
) -> dict[str, Any]:
    url = service.public_https_probe_url
    if url is None:
        raise ValueError("service is not approved for public HTTPS probing")
    result = await _probe_http_endpoint(
        client,
        semaphore,
        service_id=service.service_id,
        name=service.name,
        url=url,
    )
    if (
        not service.effective_cloudflare_access_required
        or result.get("http_status") not in _WARNING_HTTP_STATUSES
    ):
        return result

    edge_evidence = await _probe_http_edge_evidence(url)
    result.update(edge_evidence)
    if edge_evidence.get("cloudflare_service_token_access_passed") is not True:
        return result
    authenticated_status = int(
        edge_evidence.get("cloudflare_service_token_http_status") or 0
    )
    result["anonymous_http_status"] = result["http_status"]
    result["http_status"] = authenticated_status
    result["state"] = classify_public_http_status(authenticated_status)
    result["reachable"] = authenticated_status > 0
    result["public_probe_auth_mode"] = "cloudflare_service_token"
    return result


async def _probe_internal_service(
    semaphore: asyncio.Semaphore,
    service: HomelabService,
) -> dict[str, Any]:
    host = service.internal_host
    port = service.internal_port
    if not host or port is None:
        raise ValueError("service has no internal host/port target")
    started = time.perf_counter()
    writer: asyncio.StreamWriter | None = None
    try:
        async with semaphore:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=_INTERNAL_PROBE_TIMEOUT_SEC,
            )
        result: dict[str, Any] = {
            "id": service.service_id,
            "name": service.name,
            "host": host,
            "port": port,
            "reachable": True,
            "state": "ok",
        }
    except (OSError, TimeoutError) as exc:
        result = {
            "id": service.service_id,
            "name": service.name,
            "host": host,
            "port": port,
            "reachable": False,
            "state": "fail",
            "error": _short_error(exc),
        }
    finally:
        if writer is not None:
            writer.close()
            await writer.wait_closed()
    result["latency_ms"] = max(0, round((time.perf_counter() - started) * 1000))
    return result


def _probe_deadline_result(
    service: HomelabService,
    *,
    scope: Literal["public", "internal"],
) -> dict[str, Any]:
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


async def _collect_bounded_probe_batch(
    probes: list[tuple[HomelabService, asyncio.Task[dict[str, Any]]]],
    *,
    scope: Literal["public", "internal"],
    enabled: bool = True,
    eligible_count: int | None = None,
    per_probe_timeout_seconds: float = _PROBE_TIMEOUT_SEC,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Collect a rotating sample without queueing a late fan-out burst."""
    started = time.perf_counter()
    eligible = len(probes) if eligible_count is None else eligible_count
    if not probes:
        return [], _batch_summary(
            scope,
            enabled=enabled,
            eligible=eligible,
            sampled=0,
            completed=0,
            timed_out=0,
            elapsed_ms=0,
            per_probe_timeout_seconds=per_probe_timeout_seconds,
            states={"ok": 0, "warn": 0, "fail": 0},
        )

    tasks = [task for _, task in probes]
    done, pending = await asyncio.wait(tasks, timeout=_SERVICE_FANOUT_BUDGET_SEC)
    results: list[dict[str, Any]] = []
    for service, task in probes:
        if task in done:
            try:
                results.append(task.result())
            except Exception as exc:
                result = _probe_deadline_result(service, scope=scope)
                result.update(
                    timed_out=False,
                    error_kind="probe_error",
                    error=_short_error(exc),
                    exception_type=type(exc).__name__,
                )
                results.append(result)
        else:
            results.append(_probe_deadline_result(service, scope=scope))
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    states = {
        state: sum(result.get("state") == state for result in results)
        for state in ("ok", "warn", "fail")
    }
    return results, _batch_summary(
        scope,
        enabled=enabled,
        eligible=eligible,
        sampled=len(probes),
        completed=len(done),
        timed_out=len(pending),
        elapsed_ms=max(0, round((time.perf_counter() - started) * 1000)),
        per_probe_timeout_seconds=per_probe_timeout_seconds,
        states=states,
    )


def _batch_summary(
    scope: str,
    *,
    enabled: bool,
    eligible: int,
    sampled: int,
    completed: int,
    timed_out: int,
    elapsed_ms: int,
    per_probe_timeout_seconds: float,
    states: dict[str, int],
) -> dict[str, Any]:
    return {
        "scope": scope,
        "enabled": enabled,
        "eligible": eligible,
        "sampled": sampled,
        "scheduled": sampled,
        "completed": completed,
        "timed_out": timed_out,
        "rotating_sample": eligible > sampled,
        "budget_seconds": _SERVICE_FANOUT_BUDGET_SEC,
        "per_probe_timeout_seconds": per_probe_timeout_seconds,
        "max_concurrency": _MAX_PROBE_CONCURRENCY,
        "elapsed_ms": elapsed_ms,
        "states": states,
    }
