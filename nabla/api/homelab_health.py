# ruff: noqa: PLW0603 -- the module owns one lock-protected snapshot cache.

"""Cached health snapshots for external and optional internal homelab probes."""

from __future__ import annotations

import asyncio
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from nabla.api.homelab_catalog import fetch_homelab_services
from nabla.api.homelab_models import HomelabService
from nabla.api.truenas_client import observe_truenas_api
from nabla.integrations.truenas_client import truenas_host_port, truenas_url
from nabla.utils.environment import env_bool

HealthState = Literal["ok", "warn", "fail"]

_WARNING_HTTP_STATUSES = frozenset({401, 403, 407, 429})
_HEALTH_CACHE_TTL_SEC = 30.0
_MAX_PROBE_CONCURRENCY = 8
_PROBE_TIMEOUT_SEC = 5.0
_INTERNAL_PROBE_ENV = "HOMELAB_INTERNAL_PROBES_ENABLED"
_MAX_APPLICATION_BODY_BYTES = 16_384
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
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
    return env_bool(_INTERNAL_PROBE_ENV)


def truenas_http_verify_ssl() -> bool:
    """Return the TrueNAS TLS policy from the single canonical environment setting."""
    raw = os.getenv("TRUENAS_API_VERIFY_SSL", "true").strip()
    return raw.lower() in _TRUE_VALUES


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


def _is_textual_response(response: httpx.Response) -> bool:
    content_type = response.headers.get("content-type", "").lower()
    return content_type.startswith("text/") or any(
        marker in content_type
        for marker in ("application/json", "application/problem+json", "application/xml")
    )


def _application_error_from_response(response: httpx.Response) -> str | None:
    """Detect explicit application failures hidden behind a successful HTTP status."""
    if not (200 <= response.status_code <= 299) or not _is_textual_response(response):
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
    """Probe one HTTP endpoint and preserve status, TLS and application outcome."""
    started = time.perf_counter()
    try:
        async with semaphore:
            response = await client.head(
                url,
                headers={"User-Agent": "nabla-homelab-health/1.0"},
            )
            should_get = response.status_code in {405, 501} or (
                200 <= response.status_code <= 299 and _is_textual_response(response)
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
            "state": "fail" if application_error else classify_public_http_status(status),
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
            "tls_trusted": False if _looks_like_tls_error(error) else None,
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
    return await _probe_http_endpoint(
        client,
        semaphore,
        service_id=service.service_id,
        name=service.name,
        url=url,
    )


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
                asyncio.open_connection(host, port), timeout=_PROBE_TIMEOUT_SEC
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


def _truenas_internal_target(
    _services: list[HomelabService] | None = None,
) -> tuple[str, int]:
    return truenas_host_port()


async def _observe_truenas_api() -> dict[str, Any] | None:
    try:
        return await asyncio.to_thread(observe_truenas_api)
    except Exception as exc:  # Adapter/network/auth errors are health data.
        return {"reachable": False, "error": _short_error(exc)}


def _truenas_state(
    public_result: dict[str, Any],
    internal_result: dict[str, Any] | None,
    api_result: dict[str, Any] | None = None,
) -> HealthState:
    public_state = public_result.get("state")
    internal_state = internal_result.get("state") if internal_result else None
    api_reachable = api_result.get("reachable") if api_result else None
    if public_state == "fail" and (internal_state == "ok" or api_reachable is True):
        return "warn"
    if public_state == "fail":
        return "fail"
    if internal_state == "fail" or api_reachable is False:
        return "warn"
    if public_state == "warn":
        return "warn"
    return "ok"


async def _probe_truenas(
    semaphore: asyncio.Semaphore,
    *,
    internal_enabled: bool,
) -> dict[str, Any]:
    """Probe TrueNAS with its own TLS policy instead of weakening other probes."""
    configured_url = truenas_url().rstrip("/") + "/"
    timeout = httpx.Timeout(_PROBE_TIMEOUT_SEC)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        verify=truenas_http_verify_ssl(),
    ) as truenas_client:
        public_result = await _probe_http_endpoint(
            truenas_client,
            semaphore,
            service_id="truenas",
            name="TrueNAS",
            url=configured_url,
        )

    internal_result: dict[str, Any] | None = None
    if internal_enabled:
        host, port = _truenas_internal_target()
        internal_result = await _probe_internal_service(
            semaphore,
            HomelabService(
                name="TrueNAS",
                internalHost=host,
                internalPort=port,
                external=False,
            ),
        )

    api_result = await _observe_truenas_api()
    return {
        "id": "truenas",
        "state": _truenas_state(public_result, internal_result, api_result),
        "public": public_result,
        "internal": internal_result,
        "api": api_result,
        "internal_probe_enabled": internal_enabled,
        "verify_ssl": truenas_http_verify_ssl(),
    }


def _copy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    truenas = payload.get("truenas")
    truenas_copy = None
    if isinstance(truenas, dict):
        public = truenas.get("public")
        internal = truenas.get("internal")
        api = truenas.get("api")
        truenas_copy = {
            **truenas,
            "public": dict(public) if isinstance(public, dict) else public,
            "internal": dict(internal) if isinstance(internal, dict) else internal,
            "api": dict(api) if isinstance(api, dict) else api,
        }
    return {
        **payload,
        "truenas": truenas_copy,
        "services": [dict(service) for service in payload.get("services", [])],
        "internal_services": [dict(service) for service in payload.get("internal_services", [])],
    }


async def build_homelab_health_payload() -> dict[str, Any]:
    """Return cached external health, TrueNAS dependency health, and optional LAN probes."""
    global _cached_at, _cached_payload

    async with _cache_lock:
        now = time.monotonic()
        if _cached_payload is not None and (now - _cached_at) < _HEALTH_CACHE_TTL_SEC:
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
            public_results, truenas = await asyncio.gather(
                asyncio.gather(
                    *(
                        _probe_public_service(client, semaphore, service)
                        for service in public_services
                    )
                ),
                _probe_truenas(semaphore, internal_enabled=internal_enabled),
            )

        internal_results = await asyncio.gather(
            *(
                _probe_internal_service(semaphore, service)
                for service in internal_services
            )
        )
        payload: dict[str, Any] = {
            "schema_version": 2,
            "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "truenas": truenas,
            "services": public_results,
            "internal_probes_enabled": internal_enabled,
            "internal_services": internal_results,
        }
        _cached_payload = payload
        _cached_at = time.monotonic()
        return _copy_payload(payload)
