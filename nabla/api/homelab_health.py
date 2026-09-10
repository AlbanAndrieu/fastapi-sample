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

from nabla.api.health_probe_utils import is_textual_response, looks_like_tls_error
from nabla.api.homelab_catalog import fetch_homelab_services
from nabla.api.homelab_declared import DeclaredService, fetch_declared_service_catalog
from nabla.api.homelab_monitoring import public_monitoring_url
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_probe_evidence import (
    evidence_summary,
    merge_probe_evidence,
)
from nabla.api.homelab_probe_policy import (
    HEALTH_CACHE_TTL_SEC as _HEALTH_CACHE_TTL_SEC,
    INTERNAL_PROBE_TIMEOUT_SEC as _INTERNAL_PROBE_TIMEOUT_SEC,
    MAX_INTERNAL_PROBES_PER_REFRESH as _MAX_INTERNAL_PROBES_PER_REFRESH,
    MAX_PROBE_CONCURRENCY as _MAX_PROBE_CONCURRENCY,
    MAX_PUBLIC_PROBES_PER_REFRESH as _MAX_PUBLIC_PROBES_PER_REFRESH,
    PUBLIC_PROBE_TIMEOUT_SEC as _PUBLIC_PROBE_TIMEOUT_SEC,
    SERVICE_FANOUT_BUDGET_SEC as _SERVICE_FANOUT_BUDGET_SEC,
    select_probe_subset as _select_probe_subset,
)
from nabla.api.pfsense_dns_observer import observe_pfsense_dns_posture
from nabla.api.runtime_environment import homelab_runtime_detected
from nabla.api.sickz_cloudflare_edge import _probe_http_edge_evidence
from nabla.api.truenas_diagnostics import (
    append_truenas_api_stages,
    collect_truenas_network_diagnostics,
    unmeasured_truenas_network_diagnostics,
)
from nabla.api.truenas_health_observer import (
    observe_truenas_health_api as _observe_truenas_api,
    truenas_http_verify_ssl,
)
from nabla.integrations.truenas_client import (
    TrueNASSettings,
    truenas_host_port,
    truenas_url,
)
from nabla.utils.environment import env_bool

HealthState = Literal["ok", "warn", "fail"]

_WARNING_HTTP_STATUSES = frozenset({401, 403, 407, 429})
_PROBE_TIMEOUT_SEC = 5.0
_TRUENAS_DIAGNOSTICS_BUDGET_SEC = 3.0
_PFSENSE_CONTROL_PLANE_BUDGET_SEC = 5.0
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
            should_get = response.status_code in {405, 501} or (200 <= response.status_code <= 299 and is_textual_response(response))
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
            "probe_kind": "https" if url.lower().startswith("https://") else "http",
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
            "error_kind": ("timeout" if isinstance(exc, (httpx.TimeoutException, TimeoutError)) else "tls" if looks_like_tls_error(error) else "transport"),
            "probe_kind": "https" if url.lower().startswith("https://") else "http",
        }
    result["latency_ms"] = max(0, round((time.perf_counter() - started) * 1000))
    return result


async def _probe_public_service(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    service: HomelabService,
    declared: DeclaredService | None = None,
) -> dict[str, Any]:
    url = public_monitoring_url(service, declared)
    if url is None:
        raise ValueError("service is not approved for public HTTPS probing")
    result = await _probe_http_endpoint(
        client,
        semaphore,
        service_id=service.service_id,
        name=service.name,
        url=url,
    )
    result["probe_kind"] = "public_https"
    if not service.effective_cloudflare_access_required or result.get("http_status") not in _WARNING_HTTP_STATUSES:
        return result

    edge_evidence = await _probe_http_edge_evidence(url)
    result.update(edge_evidence)
    if edge_evidence.get("cloudflare_service_token_access_passed") is not True:
        return result

    authenticated_status = int(
        edge_evidence.get("cloudflare_service_token_http_status") or 0,
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
            "probe_kind": "tcp",
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
            "error_kind": "timeout" if isinstance(exc, TimeoutError) else "connect_failed",
            "probe_kind": "tcp",
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
    """Represent an uncompleted fan-out probe without claiming the service is down."""
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
    scope: Literal["public", "internal"],
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


async def _collect_bounded_probe_batch(
    probes: list[tuple[HomelabService, asyncio.Task[dict[str, Any]]]],
    *,
    scope: Literal["public", "internal"],
    enabled: bool = True,
    eligible_count: int | None = None,
    per_probe_timeout_seconds: float = _PROBE_TIMEOUT_SEC,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Collect a sampled fan-out without allowing it to consume core health."""
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
            "budget_seconds": _SERVICE_FANOUT_BUDGET_SEC,
            "per_probe_timeout_seconds": per_probe_timeout_seconds,
            "max_concurrency": _MAX_PROBE_CONCURRENCY,
            "elapsed_ms": 0,
            "states": {"ok": 0, "warn": 0, "fail": 0},
        }

    tasks = [task for _, task in probes]
    done, pending = await asyncio.wait(
        tasks,
        timeout=_SERVICE_FANOUT_BUDGET_SEC,
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
        "budget_seconds": _SERVICE_FANOUT_BUDGET_SEC,
        "per_probe_timeout_seconds": per_probe_timeout_seconds,
        "max_concurrency": _MAX_PROBE_CONCURRENCY,
        "elapsed_ms": max(0, round((time.perf_counter() - started) * 1000)),
        "states": states,
    }


def _truenas_internal_target(
    _services: list[HomelabService] | None = None,
) -> tuple[str, int]:
    return truenas_host_port()


def _truenas_state(
    public_result: dict[str, Any],
    internal_result: dict[str, Any] | None,
    api_result: dict[str, Any] | None = None,
) -> HealthState:
    public_state = public_result.get("state")
    internal_state = internal_result.get("state") if internal_result else None
    api_reachable = api_result.get("reachable") if api_result else None
    if api_reachable is False:
        return "fail"
    if public_state == "fail" and (internal_state == "ok" or api_reachable is True):
        return "warn"
    if public_state == "fail":
        return "fail"
    if internal_state == "fail":
        return "warn"
    if public_state == "warn":
        return "warn"
    return "ok"


async def _probe_truenas(
    semaphore: asyncio.Semaphore,
    *,
    internal_enabled: bool,
) -> dict[str, Any]:
    """Probe TrueNAS with its own TLS policy while overlapping independent stages."""
    configured_url = truenas_url().rstrip("/") + "/"
    timeout = httpx.Timeout(_PROBE_TIMEOUT_SEC)
    api_task = asyncio.create_task(_observe_truenas_api())
    internal_task: asyncio.Task[dict[str, Any]] | None = None
    if internal_enabled:
        host, port = _truenas_internal_target()
        internal_task = asyncio.create_task(
            _probe_internal_service(
                semaphore,
                HomelabService(
                    name="TrueNAS TCP",
                    internalHost=host,
                    internalPort=port,
                    external=False,
                ),
            ),
        )

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        verify=truenas_http_verify_ssl(),
    ) as truenas_client:
        public_result = await _probe_http_endpoint(
            truenas_client,
            semaphore,
            service_id="truenas",
            name="TrueNAS HTTPS",
            url=configured_url,
        )

    host, port = truenas_host_port()
    verify_ssl = truenas_http_verify_ssl()
    ws_path = os.getenv("TRUENAS_WS_PATH", "/api/current").strip() or "/api/current"
    websocket_uri = TrueNASSettings(
        url=truenas_url(),
        verify_ssl=verify_ssl,
        websocket_path=ws_path,
    ).websocket_uri
    diagnostics_task = asyncio.create_task(
        collect_truenas_network_diagnostics(
            host=host,
            port=port,
            websocket_uri=websocket_uri,
            verify_ssl=verify_ssl,
            public_result=public_result,
            path_mode=("direct_lan" if homelab_runtime_detected() else "public_wan_haproxy"),
        ),
    )

    api_result = await api_task
    internal_result = await internal_task if internal_task is not None else None
    try:
        diagnostics = await asyncio.wait_for(
            diagnostics_task,
            timeout=_TRUENAS_DIAGNOSTICS_BUDGET_SEC,
        )
    except TimeoutError:
        diagnostics_task.cancel()
        await asyncio.gather(diagnostics_task, return_exceptions=True)
        diagnostics = unmeasured_truenas_network_diagnostics(
            host=host,
            port=port,
            websocket_uri=websocket_uri,
            verify_ssl=verify_ssl,
            path_mode=("direct_lan" if homelab_runtime_detected() else "public_wan_haproxy"),
            budget_seconds=_TRUENAS_DIAGNOSTICS_BUDGET_SEC,
        )
    diagnostics = append_truenas_api_stages(diagnostics, api_result)
    return {
        "id": "truenas",
        "state": _truenas_state(public_result, internal_result, api_result),
        "public": public_result,
        "internal": internal_result,
        "api": api_result,
        "diagnostics": diagnostics,
        "internal_probe_enabled": internal_enabled,
        "verify_ssl": verify_ssl,
    }


async def _bounded_pfsense_posture(services: list[HomelabService]) -> dict[str, Any]:
    truenas_hosts = frozenset(service.internal_host for service in services if service.service_id == "truenas" and service.internal_host)
    try:
        async with asyncio.timeout(_PFSENSE_CONTROL_PLANE_BUDGET_SEC):
            return await observe_pfsense_dns_posture(truenas_hosts=truenas_hosts)
    except TimeoutError:
        return {
            "configured": True,
            "reachable": None,
            "policy_state": "unknown",
            "warning": "⚠️ pfSense control-plane observation exceeded its bounded probe budget",
            "error_stage": "deadline",
            "error": "timeout",
            "services": [],
        }
    except Exception as exc:  # pragma: no cover - provider/runtime dependent
        return {
            "configured": True,
            "reachable": None,
            "policy_state": "unknown",
            "warning": "⚠️ pfSense control-plane observation failed",
            "error_stage": "probe_error",
            "error": type(exc).__name__,
            "services": [],
        }


def _copy_payload(
    payload: dict[str, Any],
    *,
    cache_source: Literal["origin", "memory"],
    cache_age_seconds: float,
) -> dict[str, Any]:
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

    raw_summary = payload.get("probe_summary") or {}
    probe_summary = dict(raw_summary)
    for scope in ("public", "internal"):
        if isinstance(raw_summary.get(scope), dict):
            probe_summary[scope] = dict(raw_summary[scope])

    age = max(0.0, cache_age_seconds)
    return {
        **payload,
        "truenas": truenas_copy,
        "services": [dict(service) for service in payload.get("services", [])],
        "public_probe_results": [dict(service) for service in payload.get("public_probe_results", [])],
        "internal_services": [dict(service) for service in payload.get("internal_services", [])],
        "probe_summary": probe_summary,
        "probe_cache": {
            "source": cache_source,
            "age_seconds": round(age, 3),
            "ttl_seconds": _HEALTH_CACHE_TTL_SEC,
            "stale": age >= _HEALTH_CACHE_TTL_SEC,
        },
    }


async def build_homelab_health_payload(
    *,
    catalog_services: list[HomelabService] | None = None,
) -> dict[str, Any]:
    """Return bounded, cached homelab probes with explicit sampling metadata."""
    global _cached_at, _cached_payload

    async with _cache_lock:
        now = time.monotonic()
        if _cached_payload is not None and (now - _cached_at) < _HEALTH_CACHE_TTL_SEC:
            return _copy_payload(
                _cached_payload,
                cache_source="memory",
                cache_age_seconds=now - _cached_at,
            )

        refresh_started = time.perf_counter()
        if catalog_services is not None:
            services = list(catalog_services)
            declared_catalog = await fetch_declared_service_catalog()
        else:
            services, declared_catalog = await asyncio.gather(
                fetch_homelab_services(),
                fetch_declared_service_catalog(),
            )
        declared_by_id = {item.service_id: item for item in declared_catalog.services}
        public_candidates = [service for service in services if service.public_https_probe_url is not None]
        internal_candidates = [service for service in services if service.internal_host and service.internal_port is not None]
        internal_enabled = internal_probes_enabled()
        public_services = _select_probe_subset(
            public_candidates,
            limit=_MAX_PUBLIC_PROBES_PER_REFRESH,
        )
        internal_services = (
            _select_probe_subset(
                internal_candidates,
                limit=_MAX_INTERNAL_PROBES_PER_REFRESH,
            )
            if internal_enabled
            else []
        )

        service_semaphore = asyncio.Semaphore(_MAX_PROBE_CONCURRENCY)
        truenas_semaphore = asyncio.Semaphore(2)
        truenas_task = asyncio.create_task(
            _probe_truenas(
                truenas_semaphore,
                internal_enabled=internal_enabled,
            ),
        )
        pfsense_task = asyncio.create_task(_bounded_pfsense_posture(services))
        internal_probe_tasks = [
            (
                service,
                asyncio.create_task(
                    _probe_internal_service(service_semaphore, service),
                ),
            )
            for service in internal_services
        ]
        internal_results_task = asyncio.create_task(
            _collect_bounded_probe_batch(
                internal_probe_tasks,
                scope="internal",
                enabled=internal_enabled,
                eligible_count=len(internal_candidates),
                per_probe_timeout_seconds=_INTERNAL_PROBE_TIMEOUT_SEC,
            ),
        )

        timeout = httpx.Timeout(_PUBLIC_PROBE_TIMEOUT_SEC)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            public_probe_tasks = [
                (
                    service,
                    asyncio.create_task(
                        _probe_public_service(
                            client,
                            service_semaphore,
                            service,
                            declared_by_id.get(service.service_id),
                        ),
                    ),
                )
                for service in public_services
            ]
            public_results_task = asyncio.create_task(
                _collect_bounded_probe_batch(
                    public_probe_tasks,
                    scope="public",
                    eligible_count=len(public_candidates),
                    per_probe_timeout_seconds=_PUBLIC_PROBE_TIMEOUT_SEC,
                ),
            )
            (
                (public_results, public_summary),
                truenas,
                (
                    internal_results,
                    internal_summary,
                ),
                pfsense_dns,
            ) = await asyncio.gather(
                public_results_task,
                truenas_task,
                internal_results_task,
                pfsense_task,
            )

        checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        public_results = merge_probe_evidence(
            "public",
            current_results=public_results,
            eligible_services=public_candidates,
            checked_at=checked_at,
        )
        internal_results = (
            merge_probe_evidence(
                "internal",
                current_results=internal_results,
                eligible_services=internal_candidates,
                checked_at=checked_at,
            )
            if internal_enabled
            else []
        )
        public_summary["evidence"] = evidence_summary(
            public_results,
            eligible_count=len(public_candidates),
        )
        internal_summary["evidence"] = evidence_summary(
            internal_results,
            eligible_count=len(internal_candidates),
        )

        payload: dict[str, Any] = {
            "schema_version": 3,
            "checked_at": checked_at,
            "refresh_elapsed_ms": max(
                0,
                round((time.perf_counter() - refresh_started) * 1000),
            ),
            "truenas": truenas,
            "pfsense": {"dns": pfsense_dns},
            "services": public_results,
            "public_probe_results": public_results,
            "internal_probes_enabled": internal_enabled,
            "internal_services": internal_results,
            "probe_summary": {
                "public": public_summary,
                "internal": internal_summary,
                "catalog_service_count": len(services),
                "sampling": {
                    "strategy": "priority-plus-rotating-window",
                    "cache_ttl_seconds": _HEALTH_CACHE_TTL_SEC,
                },
            },
        }
        _cached_payload = payload
        _cached_at = time.monotonic()
        return _copy_payload(
            payload,
            cache_source="origin",
            cache_age_seconds=0.0,
        )
