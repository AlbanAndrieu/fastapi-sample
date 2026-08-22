"""Cached health snapshots for external and optional internal homelab probes."""

from __future__ import annotations

import asyncio
import os
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
_INTERNAL_PROBE_ENV = "HOMELAB_INTERNAL_PROBES_ENABLED"

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


def internal_probes_enabled() -> bool:
    """Return whether internal TCP probes are explicitly enabled for this runtime."""
    return os.getenv(_INTERNAL_PROBE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


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


async def _probe_internal_service(
    semaphore: asyncio.Semaphore,
    service: HomelabService,
) -> dict[str, Any]:
    """Probe catalog-declared internal host/port reachability using TCP only."""
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
                timeout=_PROBE_TIMEOUT_SEC,
            )
        result: dict[str, Any] = {
            "name": service.name,
            "host": host,
            "port": port,
            "reachable": True,
            "state": "ok",
        }
    except (OSError, TimeoutError) as exc:
        result = {
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


def _copy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe copy so callers cannot mutate cached probe rows."""
    return {
        **payload,
        "services": [dict(service) for service in payload.get("services", [])],
        "internal_services": [
            dict(service) for service in payload.get("internal_services", [])
        ],
    }


async def build_homelab_health_payload() -> dict[str, Any]:
    """Return cached external health plus optional internal TCP reachability."""
    global _cached_at, _cached_payload

    async with _cache_lock:
        now = time.monotonic()
        if (
            _cached_payload is not None
            and (now - _cached_at) < _HEALTH_CACHE_TTL_SEC
        ):
            return _copy_payload(_cached_payload)

        catalog_services = await fetch_homelab_services()
        public_services = [
            service
            for service in catalog_services
            if service.public_https_probe_url is not None
        ]
        internal_enabled = internal_probes_enabled()
        internal_services = [
            service
            for service in catalog_services
            if internal_enabled
            and service.internal_host
            and service.internal_port is not None
        ]

        semaphore = asyncio.Semaphore(_MAX_PROBE_CONCURRENCY)
        timeout = httpx.Timeout(_PROBE_TIMEOUT_SEC)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            public_results = await asyncio.gather(
                *(
                    _probe_public_service(client, semaphore, service)
                    for service in public_services
                )
            )

        internal_results = await asyncio.gather(
            *(
                _probe_internal_service(semaphore, service)
                for service in internal_services
            )
        )

        payload: dict[str, Any] = {
            "schema_version": 1,
            "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "services": public_results,
            "internal_probes_enabled": internal_enabled,
            "internal_services": internal_results,
        }
        _cached_payload = payload
        _cached_at = time.monotonic()
        return _copy_payload(payload)
