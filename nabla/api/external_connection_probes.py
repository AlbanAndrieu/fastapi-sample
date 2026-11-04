"""Fixed, cached, outside-in checks from the explicitly trusted TrueNAS runtime.

These are public endpoints only. No arbitrary URL, internal IP, Cloudflare token,
or browser-provided target can reach this module.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
import time
from typing import Any

import httpx

from nabla.api.platform_health_diagnostics import utc_now
from nabla.api.runtime_environment import homelab_runtime_detected

_CLOUD_SESSION_URL = "https://fastapi-sample.fastapicloud.dev/api/ui/session"
_DOH_URL = "https://cloudflare-dns.com/dns-query"
_DNS_HOSTS = ("sample.albandrieu.com", "fastapi-sample.fastapicloud.dev")
_TIMEOUT_SECONDS = 2.5
_CACHE_TTL_SECONDS = 90.0
_lock = asyncio.Lock()


@dataclass(slots=True)
class _Cache:
    payload: dict[str, Any] | None = None
    created_monotonic: float = 0.0


_cache = _Cache()


def _http_category(status: int) -> str:
    if status in (301, 302, 303, 307, 308, 401, 403):
        return "access_protected"
    if status == 429:
        return "rate_limited"
    if status >= 500:
        return "http_failure"
    if status >= 400:
        return "http_rejected"
    return "origin_unverified"


async def _probe_cloud_session(client: httpx.AsyncClient) -> dict[str, Any]:
    """Read the anonymous session contract; never claim authenticated access."""
    try:
        response = await client.get(
            _CLOUD_SESSION_URL,
            headers={"Accept": "application/json"},
            follow_redirects=False,
        )
        status = response.status_code
        if status != 200:
            return {
                "state": "warn" if status < 500 else "fail",
                "category": _http_category(status),
                "http_status": status,
                "origin_verified": False,
            }
        if "application/json" not in response.headers.get("content-type", "").lower():
            return {
                "state": "unknown",
                "category": "unexpected_content",
                "http_status": status,
                "origin_verified": False,
            }
        payload = response.json()
        valid = isinstance(payload, dict) and type(payload.get("authenticated")) is bool
        return {
            "state": "ok" if valid else "unknown",
            "category": "anonymous_api_observed" if valid else "unexpected_json",
            "http_status": status,
            "origin_verified": valid,
        }
    except (httpx.HTTPError, OSError, ValueError, TypeError) as exc:
        return {
            "state": "unknown",
            "category": "probe_timeout" if isinstance(exc, httpx.TimeoutException) else "probe_error",
            "exception_type": type(exc).__name__,
            "origin_verified": False,
        }


async def _probe_cloudflare_resolver(
    client: httpx.AsyncClient, hostname: str,
) -> dict[str, Any]:
    """Cloudflare recursive DoH resolver evidence, NOT authoritative-zone health."""
    try:
        response = await client.get(
            _DOH_URL,
            params={"name": hostname, "type": "A"},
            headers={"Accept": "application/dns-json"},
            follow_redirects=False,
        )
        if response.status_code != 200:
            return {
                "state": "unknown",
                "category": _http_category(response.status_code),
                "http_status": response.status_code,
            }
        payload = response.json()
        if not isinstance(payload, dict) or type(payload.get("Status")) is not int:
            return {"state": "unknown", "category": "invalid_dns_payload"}
        rcode = payload["Status"]
        answers = payload.get("Answer")
        record_count = sum(
            type(answer.get("type")) is int and answer["type"] == 1
            and isinstance(answer.get("data"), str)
            for answer in answers
            if isinstance(answer, dict)
        ) if isinstance(answers, list) else 0
        if rcode == 3:
            state, category = "fail", "nxdomain"
        elif rcode == 0 and record_count > 0:
            state, category = "ok", "public_dns_observed"
        elif rcode == 0:
            state, category = "unknown", "no_a_answer"
        else:
            state, category = "unknown", "dns_rcode_error"
        return {
            "state": state,
            "category": category,
            "rcode": rcode,
            "a_record_count": min(record_count, 32),
        }
    except (httpx.HTTPError, OSError, ValueError, TypeError) as exc:
        return {
            "state": "unknown",
            "category": "probe_timeout" if isinstance(exc, httpx.TimeoutException) else "probe_error",
            "exception_type": type(exc).__name__,
        }


async def _probe_origin(client: httpx.AsyncClient) -> dict[str, Any]:
    cloud, *dns_results = await asyncio.gather(
        _probe_cloud_session(client),
        *(_probe_cloudflare_resolver(client, host) for host in _DNS_HOSTS),
    )
    return {
        "state": "observed",
        "observed_at": utc_now(),
        "scope": "outside_in_from_truenas",
        "cloud": cloud,
        "cloudflare_public_dns": dict(zip(_DNS_HOSTS, dns_results, strict=True)),
        "dns_source": "cloudflare_recursive_doh_not_authoritative_zone",
    }


async def fetch_external_connection_probes(
    *, client: httpx.AsyncClient | None = None, enabled: bool | None = None,
) -> dict[str, Any]:
    """Single-flight with 90s caching; disabled outside explicitly trusted LAN.

    The injected client is used only for deterministic tests. Production clients
    always disable ambient proxy, redirects, and unbounded request duration.
    """
    trusted = homelab_runtime_detected() if enabled is None else enabled
    if not trusted:
        return {
            "state": "not_executed",
            "scope": "not_trusted_homelab",
            "cloud": {"state": "unknown", "category": "not_executed"},
            "cloudflare_public_dns": {},
        }
    if client is not None:
        return await _probe_origin(client)

    now = time.monotonic()
    if _cache.payload is not None and now - _cache.created_monotonic < _CACHE_TTL_SECONDS:
        return {**deepcopy(_cache.payload), "cache_source": "memory",
                "cache_age_seconds": round(now - _cache.created_monotonic, 3)}
    async with _lock:
        now = time.monotonic()
        if _cache.payload is not None and now - _cache.created_monotonic < _CACHE_TTL_SECONDS:
            return {**deepcopy(_cache.payload), "cache_source": "memory",
                    "cache_age_seconds": round(now - _cache.created_monotonic, 3)}
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(_TIMEOUT_SECONDS),
                follow_redirects=False,
                trust_env=False,
            ) as probe_client:
                payload = await asyncio.wait_for(_probe_origin(probe_client), timeout=3.0)
        except (TimeoutError, httpx.HTTPError) as exc:
            payload = {
                "state": "unavailable",
                "observed_at": utc_now(),
                "scope": "outside_in_from_truenas",
                "cloud": {"state": "unknown", "category": "probe_error",
                          "exception_type": type(exc).__name__},
                "cloudflare_public_dns": {},
            }
        _cache.payload = payload
        _cache.created_monotonic = time.monotonic()
        return {**deepcopy(payload), "cache_source": "origin",
                "cache_age_seconds": 0.0}


def reset_external_connection_probes() -> None:
    """Clear process cache during deterministic unit tests."""
    _cache.payload = None
    _cache.created_monotonic = 0.0
