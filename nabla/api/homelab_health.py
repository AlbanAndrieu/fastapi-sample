"""Cached public health snapshot for externally exposed homelab services."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from nabla.api.homelab_catalog import fetch_homelab_services
from nabla.api.homelab_models import HomelabService

HealthState = Literal["ok", "warn", "fail"]

_WARNING_HTTP_STATUSES = frozenset({401, 403, 407, 429})
_HEALTH_CACHE_TTL_SEC = 30.0
_MAX_PROBE_CONCURRENCY = 8
_PROBE_TIMEOUT_SEC = 5.0

_cache_lock = asyncio.Lock()
_cached_at = 0.0
_cached_payload: dict[str, Any] | None = None


def classify_public_http_status(status: int) -> HealthState:
    """Map an endpoint HTTP status to the public site health state."""
    if 200 <= status <= 399:
        return "ok"
    if status in _WARNING_HTTP_STATUSES:
        return "warn"
    return "fail"


def _looks_like_tls_error(message: str) -> bool:
    lower = message.lower()
    return any(
        marker in lower
        for marker in (
            "certificate",
            "cert verify",
            "hostname mismatch",
            "ssl",
            "tls",
            "unable to verify",
        )
    )


def _short_error(exc: BaseException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:240]


async def _probe_public_service(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    service: HomelabService,
) -> dict[str, Any]:
    """Probe one catalog-approved public endpoint and preserve its real HTTP status."""
    url = service.public_https_probe_url
    if url is None:
        raise ValueError("service is not approved for public HTTPS probing")

    started = time.perf_counter()
    try:
        async with semaphore:
            response = await client.head(
                url,
                headers={"User-Agent": "nabla-homelab-health/1.0"},
            )
            if response.status_code in {405, 501}:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "nabla-homelab-health/1.0",
                        "Range": "bytes=0-0",
                        "Accept": "*/*",
                    },
                )
        status = response.status_code
        result: dict[str, Any] = {
            "name": service.name,
            "url": url,
            "reachable": True,
            "http_status": status,
            "state": classify_public_http_status(status),
            "tls_trusted": True,
        }
    except (httpx.HTTPError, OSError) as exc:
        error = _short_error(exc)
        result = {
            "name": service.name,
            "url": url,
            "reachable": False,
            "http_status": 0,
            "state": "fail",
            "tls_trusted": False if _looks_like_tls_error(error) else None,
            "error": error,
        }

    result["latency_ms"] = max(0, round((time.perf_counter() - started) * 1000))
    return result


def _copy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow JSON-safe copy so callers cannot mutate the cache."""
    return {
        **payload,
        "services": [dict(service) for service in payload.get("services", [])],
    }


async def build_homelab_health_payload() -> dict[str, Any]:
    """Return a cached health snapshot for explicitly public homelab endpoints."""
    global _cached_at, _cached_payload

    async with _cache_lock:
        now = time.monotonic()
        if (
            _cached_payload is not None
            and (now - _cached_at) < _HEALTH_CACHE_TTL_SEC
        ):
            return _copy_payload(_cached_payload)

        services = [
            service
            for service in await fetch_homelab_services()
            if service.public_https_probe_url is not None
        ]
        semaphore = asyncio.Semaphore(_MAX_PROBE_CONCURRENCY)
        timeout = httpx.Timeout(_PROBE_TIMEOUT_SEC)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            results = await asyncio.gather(
                *(
                    _probe_public_service(client, semaphore, service)
                    for service in services
                )
            )

        payload: dict[str, Any] = {
            "schema_version": 1,
            "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "services": results,
        }
        _cached_payload = payload
        _cached_at = time.monotonic()
        return _copy_payload(payload)
