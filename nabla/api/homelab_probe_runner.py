"""Low-level bounded HTTP/TCP probe execution for homelab health."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import re
import time
from typing import Any, Literal

import httpx

from nabla.api.dns_probe import probe_dns_hostname
from nabla.api.health_probe_utils import is_textual_response, looks_like_tls_error
from nabla.api.homelab_models import HomelabService

HealthState = Literal["ok", "warn", "fail"]
ProbeScope = Literal["public", "internal"]
HttpProbe = Callable[..., Awaitable[dict[str, Any]]]
EdgeProbe = Callable[[str], Awaitable[dict[str, Any]]]


_WARNING_HTTP_STATUSES = frozenset({401, 403, 407, 429})
_ACCESS_EDGE_HTTP_STATUSES = _WARNING_HTTP_STATUSES | frozenset(
    {301, 302, 303, 307, 308}
)
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
    """Map an endpoint HTTP status to the public site health state."""
    if 200 <= status <= 399:
        return "ok"
    if status in _WARNING_HTTP_STATUSES:
        return "warn"
    return "fail"


def _short_error(exc: BaseException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:240]


def _application_error_from_response(response: httpx.Response) -> str | None:
    """Detect explicit application failures hidden behind a successful HTTP status."""
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
    if any(
        lowered_plain.startswith(prefix)
        for prefix in _APPLICATION_ERROR_PREFIXES
    ):
        return plain[:240]
    if any(marker in lowered_raw for marker in _APPLICATION_ERROR_MARKERS):
        return plain[:240]
    if re.search(
        r"<(?:title|h1)[^>]*>\s*(?:error|fatal|exception|application error|"
        r"internal server error|bad gateway|service unavailable)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return plain[:240]
    return None


async def probe_http_endpoint(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    *,
    service_id: str,
    name: str,
    url: str,
) -> dict[str, Any]:
    """Probe one HTTP endpoint and preserve DNS, TLS and application outcome."""
    started = time.perf_counter()
    dns_evidence: dict[str, Any] = {}
    try:
        async with semaphore:
            hostname = httpx.URL(url).host
            if hostname:
                dns_evidence = await probe_dns_hostname(hostname)
            response = await client.head(
                url,
                headers={"User-Agent": "nabla-homelab-health/1.0"},
            )
            should_get = response.status_code in {405, 501} or (
                200 <= response.status_code <= 299
                and is_textual_response(response)
            )
            if should_get:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "nabla-homelab-health/1.0",
                        "Range": f"bytes=0-{_MAX_APPLICATION_BODY_BYTES - 1}",
                        "Accept": (
                            "text/html,text/plain,application/json,*/*;q=0.1"
                        ),
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
                "fail"
                if application_error
                else classify_public_http_status(status)
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
    result.update(dns_evidence)
    result["latency_ms"] = max(
        0,
        round((time.perf_counter() - started) * 1000),
    )
    return result


async def probe_public_service(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    service: HomelabService,
    *,
    http_probe: HttpProbe,
    edge_probe: EdgeProbe,
) -> dict[str, Any]:
    """Probe one approved public service, including Cloudflare Access evidence."""
    url = service.public_https_probe_url
    if url is None:
        raise ValueError("service is not approved for public HTTPS probing")
    result = await http_probe(
        client,
        semaphore,
        service_id=service.service_id,
        name=service.name,
        url=url,
    )
    initial_status = int(result.get("http_status") or 0)
    needs_edge_probe = (
        service.effective_cloudflare_access_required
        and initial_status in _ACCESS_EDGE_HTTP_STATUSES
    )
    if not needs_edge_probe:
        return result

    edge_evidence = await edge_probe(url)
    result.update(edge_evidence)
    result["anonymous_http_status"] = int(
        edge_evidence.get("anonymous_initial_http_status") or initial_status,
    )
    if edge_evidence.get("cloudflare_service_token_access_passed") is not True:
        default_deny = edge_evidence.get("cloudflare_default_deny") is True
        access_signal = edge_evidence.get("cloudflare_access_signal") is True
        if access_signal or default_deny:
            result["state"] = "warn"
            result["origin_reached"] = False
            result["public_probe_auth_mode"] = "cloudflare_access_blocked"
        return result

    authenticated_status = int(
        edge_evidence.get("authenticated_http_status")
        or edge_evidence.get("cloudflare_service_token_http_status")
        or 0,
    )
    result["http_status"] = authenticated_status
    result["state"] = classify_public_http_status(authenticated_status)
    result["reachable"] = authenticated_status > 0
    result["origin_reached"] = edge_evidence.get("origin_reached") is True
    result["public_probe_auth_mode"] = "cloudflare_service_token"
    return result


async def probe_internal_service(
    semaphore: asyncio.Semaphore,
    service: HomelabService,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Probe one internal TCP target under the supplied timeout budget."""
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
                timeout=timeout_seconds,
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
    result["latency_ms"] = max(
        0,
        round((time.perf_counter() - started) * 1000),
    )
    return result


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
            "error": _short_error(exc),
            "exception_type": type(exc).__name__,
        },
    )
    return result


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

    states = {
        state: sum(result.get("state") == state for result in results)
        for state in ("ok", "warn", "fail")
    }
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
        "elapsed_ms": max(
            0,
            round((time.perf_counter() - started) * 1000),
        ),
        "states": states,
    }
