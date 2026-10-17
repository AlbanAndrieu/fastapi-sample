"""Low-level bounded HTTP/TCP probe execution for homelab health."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import re
import time
from typing import Any, Literal

import anyio
import httpx

from nabla.api.dns_probe import probe_dns_hostname
from nabla.api.health_probe_utils import elapsed_ms, is_textual_response, looks_like_tls_error
from nabla.api.homelab_models import HomelabService
from nabla.api.platform_health_diagnostics import short_error

HealthState = Literal["ok", "warn", "fail"]
HttpProbe = Callable[..., Awaitable[dict[str, Any]]]
EdgeProbe = Callable[[str], Awaitable[dict[str, Any]]]


_WARNING_HTTP_STATUSES = frozenset({401, 403, 407, 429})
_ACCESS_EDGE_HTTP_STATUSES = _WARNING_HTTP_STATUSES | frozenset(
    {301, 302, 303, 307, 308},
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
            value = payload.get("error") or payload.get("errors") or payload.get("exception")
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
    """Probe HTTP and measure scheduling separately from DNS and HTTP I/O."""
    started = time.perf_counter()
    dns_evidence: dict[str, Any] = {}
    queue_wait_ms: int | None = None
    dns_probe_ms: int | None = None
    http_request_ms: int | None = None
    request_count = 0
    try:
        async with semaphore:
            queue_wait_ms = elapsed_ms(started)
            hostname = httpx.URL(url).host
            dns_started = time.perf_counter()
            try:
                if hostname:
                    dns_evidence = await probe_dns_hostname(hostname)
            finally:
                dns_probe_ms = elapsed_ms(dns_started)
            http_started = time.perf_counter()
            try:
                request_count += 1
                response = await client.head(
                    url,
                    headers={"User-Agent": "nabla-homelab-health/1.0"},
                )
                should_get = response.status_code in {405, 501} or (200 <= response.status_code <= 299 and is_textual_response(response))
                if should_get:
                    request_count += 1
                    response = await client.get(
                        url,
                        headers={
                            "User-Agent": "nabla-homelab-health/1.0",
                            "Range": f"bytes=0-{_MAX_APPLICATION_BODY_BYTES - 1}",
                            "Accept": "text/html,text/plain,application/json,*/*;q=0.1",
                        },
                    )
            finally:
                http_request_ms = elapsed_ms(http_started)
        status = response.status_code
        application_error = _application_error_from_response(response)
        result: dict[str, Any] = {
            "id": service_id,
            "name": name,
            "url": url,
            "reachable": True,
            "http_status": status,
            "state": ("fail" if application_error else classify_public_http_status(status)),
            "tls_trusted": True,
        }
        if application_error:
            result["application_error"] = application_error
    except (httpx.HTTPError, OSError) as exc:
        error = short_error(exc)
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
    # Missing phase timing means the phase did not finish (or never started),
    # not zero latency. Never expose DNS answers, headers or body in timings.
    result["probe_timing"] = {
        "queue_wait_ms": queue_wait_ms,
        "dns_probe_ms": dns_probe_ms,
        "http_request_ms": http_request_ms,
        "http_request_count": request_count,
    }
    result["latency_ms"] = elapsed_ms(started)
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
    needs_edge_probe = service.effective_cloudflare_access_required and initial_status in _ACCESS_EDGE_HTTP_STATUSES
    result["cloudflare_access_secondary_probe_eligible"] = needs_edge_probe
    result["cloudflare_access_secondary_probe_attempted"] = False
    if not needs_edge_probe:
        return result

    result["cloudflare_access_secondary_probe_attempted"] = True
    edge_started = time.perf_counter()
    edge_evidence = await edge_probe(url)
    # This call is deliberately outside the HTTP semaphore. Account for that
    # extra latency independently rather than assuming TCP/DNS is slow.
    timing = result.get("probe_timing")
    if isinstance(timing, dict):
        timing["access_secondary_ms"] = elapsed_ms(edge_started)
    result.update(edge_evidence)
    result["anonymous_http_status"] = int(
        edge_evidence.get("anonymous_initial_http_status") or initial_status,
    )
    if edge_evidence.get("cloudflare_service_token_access_passed") is not True:
        default_deny = edge_evidence.get("cloudflare_default_deny") is True
        access_signal = edge_evidence.get("cloudflare_access_signal") is True
        result["state"] = "warn"
        result["origin_reached"] = False
        result["cloudflare_service_token_rejected"] = edge_evidence.get("cloudflare_service_auth_attempted") is True and edge_evidence.get(
            "cloudflare_service_token_http_status",
        ) in {401, 403}
        result["public_probe_auth_mode"] = "cloudflare_access_blocked" if access_signal or default_deny else "cloudflare_access_unconfirmed"
        result["public_probe_verification"] = "access_protected_origin_unverified" if access_signal or default_deny else "origin_unverified"
        return result

    authenticated_status = int(
        edge_evidence.get("authenticated_http_status") or edge_evidence.get("cloudflare_service_token_http_status") or 0,
    )
    result["http_status"] = authenticated_status
    result["state"] = classify_public_http_status(authenticated_status) if authenticated_status > 0 else "warn"
    # A successful Access handshake alone is not proof of a healthy origin.
    if authenticated_status >= 200 and authenticated_status < 400 and edge_evidence.get("origin_reached") is not True:
        result["state"] = "warn"
    result["reachable"] = authenticated_status > 0
    result["origin_reached"] = edge_evidence.get("origin_reached") is True
    result["public_probe_auth_mode"] = "cloudflare_service_token"
    result["public_probe_verification"] = "authenticated_origin_observed" if result["origin_reached"] else "authenticated_origin_unverified"
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
    try:
        async with semaphore:
            with anyio.fail_after(timeout_seconds):
                stream = await anyio.connect_tcp(host, port)
                await stream.aclose()
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
            "error": short_error(exc),
        }
    result["latency_ms"] = elapsed_ms(started)
    return result
