"""Core dependency probes and orchestration for the extended ``/healthz`` endpoint."""

from __future__ import annotations

import asyncio
import logging
import socket
import ssl
import time
from typing import Any

import httpx
from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.engine import Engine

from nabla.api.auth.openstack import probe_ovh_me_reachable
from nabla.api.health_probe_utils import (
    normalize_probe_error as _normalize_probe_error,
    normalize_probe_result_errors as _normalize_probe_result_errors,
)
from nabla.api.homelab_catalog import homelab_healthz_probe_rows
from nabla.api.integration_health import (
    enrich_integration_metadata,
    probe_appwrite_health,
    probe_brave_search,
    probe_datadog_trace_agent,
    probe_google_cse,
    probe_keycloak_well_known,
    probe_litellm_public_proxy,
    probe_pyroscope_server,
    probe_sentry_reachable,
    probe_tavily_search,
    probe_unleash_client_features,
)
from nabla.config_settings import REDIS_URL, get_settings

logger = logging.getLogger(__name__)


def _exception_chain(exc: BaseException) -> list[BaseException]:
    """Return ``exc`` plus chained causes/contexts without looping forever."""
    chain: list[BaseException] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return chain


def _probe_failure_stage(exc: BaseException) -> str:
    """Classify a failed network probe into a useful operational stage."""
    chain = _exception_chain(exc)
    message = " ".join(str(item) for item in chain).casefold()

    if any(isinstance(item, socket.gaierror) for item in chain) or any(
        marker in message
        for marker in (
            "name or service not known",
            "temporary failure in name resolution",
            "nodename nor servname provided",
            "getaddrinfo failed",
        )
    ):
        return "dns"
    if any(isinstance(item, ssl.SSLError) for item in chain) or any(
        marker in message
        for marker in (
            "certificate verify failed",
            "hostname mismatch",
            "ssl:",
            "tls",
        )
    ):
        return "tls"
    if isinstance(exc, httpx.ConnectTimeout):
        return "connect_timeout"
    if isinstance(exc, httpx.ReadTimeout):
        return "read_timeout"
    if isinstance(exc, httpx.WriteTimeout):
        return "write_timeout"
    if isinstance(exc, httpx.PoolTimeout):
        return "pool_timeout"
    if "connection refused" in message:
        return "connect_refused"
    if "network is unreachable" in message or "no route to host" in message:
        return "network_unreachable"
    if isinstance(exc, httpx.ConnectError):
        return "connect"
    if isinstance(exc, httpx.RemoteProtocolError):
        return "protocol"
    if isinstance(exc, httpx.TimeoutException) or any(
        isinstance(item, TimeoutError) for item in chain
    ):
        return "timeout"
    if isinstance(exc, httpx.HTTPError):
        return "http_client"
    return "network"


async def probe_https_get_reachable(
    url: str,
    *,
    probe_name: str | None = None,
) -> dict[str, Any]:
    """GET ``url`` and expose timing plus the exact network failure stage."""
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0),
            follow_redirects=True,
        ) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "nabla-healthz-probe/1.0"},
            )
    except (httpx.HTTPError, OSError) as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        stage = _probe_failure_stage(exc)
        result = {
            "reachable": False,
            "error": _normalize_probe_error(str(exc)),
            "exception_type": exc.__class__.__name__,
            "failure_stage": stage,
            "elapsed_ms": elapsed_ms,
            "url": url,
        }
        if (probe_name or "").casefold() == "truenas":
            logger.warning(
                "TrueNAS HTTP probe failed url=%s stage=%s exception=%s elapsed_ms=%s error=%s",
                url,
                stage,
                exc.__class__.__name__,
                elapsed_ms,
                result["error"],
            )
        return result

    elapsed_ms = round((time.perf_counter() - started) * 1000)
    result = {
        "reachable": True,
        "http_status": response.status_code,
        "url": url,
        "final_url": str(response.url),
        "redirects": len(response.history),
        "elapsed_ms": elapsed_ms,
    }
    if (probe_name or "").casefold() == "truenas":
        logger.info(
            "TrueNAS HTTP probe succeeded url=%s final_url=%s status=%s redirects=%s elapsed_ms=%s",
            url,
            response.url,
            response.status_code,
            len(response.history),
            elapsed_ms,
        )
    return result


def _tls_trusted_from_https_probe_result(
    result: dict[str, Any],
    url: str,
) -> bool | None:
    """Infer CA-trusted TLS from a probe made with default verification."""
    if not (url or "").strip().lower().startswith("https:"):
        return None
    if result.get("skipped"):
        return None
    if result.get("reachable") is True:
        return True
    if result.get("failure_stage") == "tls":
        return False
    error = str(result.get("error") or "").lower()
    markers = ("ssl", "certificate", "tls", "cert verify", "hostname mismatch")
    return False if any(marker in error for marker in markers) else None


async def fetch_base_health(request: Request) -> dict[str, Any]:
    """GET ``/health`` on this app using the incoming scheme/host/port."""
    url = str(request.url.replace(path="/health", query="", fragment=""))
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        return {
            "status": "health_fetch_failed",
            "error": _normalize_probe_error(str(exc)),
        }
    if response.status_code != 200:
        return {
            "status": "health_endpoint_non_200",
            "http_status": response.status_code,
        }
    try:
        body = response.json()
    except ValueError:
        return {"status": "health_invalid_json", "http_status": response.status_code}
    if not isinstance(body, dict):
        return {
            "status": "health_unexpected_shape",
            "http_status": response.status_code,
        }
    return body


async def check_redis_ping(redis_client: Any) -> dict[str, Any]:
    if not (REDIS_URL or "").strip():
        return {
            "reachable": None,
            "skipped": True,
            "reason": "REDIS_URL not configured (empty)",
        }
    if redis_client is None:
        return {"reachable": False, "error": "redis client not initialized"}
    try:
        ok = await redis_client.ping()
        return {"reachable": bool(ok)}
    except Exception as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}


def check_postgres_sql(engine: Engine) -> dict[str, Any]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"reachable": True}
    except Exception as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}


async def check_supabase_http() -> dict[str, Any]:
    """Probe the Supabase Data API with the least-privileged configured API key."""
    settings = get_settings()
    base_url = (settings.supabase_url or "").strip()
    if not base_url:
        return {
            "reachable": None,
            "skipped": True,
            "reason": "SUPABASE_URL not configured",
        }
    health_table = getattr(settings, "supabase_health_table", "note")
    health_url = f"{base_url.rstrip('/')}/rest/v1/{health_table}"
    publishable_key = getattr(settings, "supabase_publishable_key", None)
    service_role_key = getattr(settings, "supabase_service_role_key", None)
    key_source = None
    api_key = ""
    if publishable_key is not None:
        api_key = publishable_key.get_secret_value().strip()
        key_source = "publishable_key" if api_key else None
    if not api_key and service_role_key is not None:
        api_key = service_role_key.get_secret_value().strip()
        key_source = "service_role_key" if api_key else None
    if not api_key:
        return {
            "reachable": None,
            "skipped": True,
            "reason": (
                "SUPABASE_PUBLISHABLE_KEY and SUPABASE_SERVICE_ROLE_KEY "
                "are not configured"
            ),
            "probe": "data_api",
        }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                health_url,
                headers={"apikey": api_key, "Accept": "application/json"},
                params={"select": "id", "limit": "0"},
            )
    except httpx.HTTPError as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}
    return {
        "reachable": response.status_code < 400,
        "http_status": response.status_code,
        "probe": "data_api",
        "authentication": key_source,
        "resource": health_table,
        "path": f"/rest/v1/{health_table}",
    }


async def _run_dependency_probes(
    redis_client: Any,
    engine: Engine,
) -> tuple[dict[str, Any], ...]:
    """Run core and optional integration probes concurrently."""
    return await asyncio.gather(
        check_redis_ping(redis_client),
        run_in_threadpool(check_postgres_sql, engine),
        check_supabase_http(),
        run_in_threadpool(probe_ovh_me_reachable),
        run_in_threadpool(probe_tavily_search),
        run_in_threadpool(probe_brave_search),
        run_in_threadpool(probe_google_cse),
        run_in_threadpool(probe_appwrite_health),
        run_in_threadpool(probe_keycloak_well_known),
        run_in_threadpool(probe_unleash_client_features),
        run_in_threadpool(probe_sentry_reachable),
        run_in_threadpool(probe_datadog_trace_agent),
        run_in_threadpool(probe_pyroscope_server),
        run_in_threadpool(probe_litellm_public_proxy),
    )


def _dependency_checks(results: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    """Map dependency probe results to the stable public check keys."""
    keys = (
        "redis",
        "postgres",
        "supabase",
        "openstack_me",
        "tavily",
        "brave",
        "google",
        "appwrite",
        "keycloak",
        "unleash",
        "sentry",
        "datadog",
        "pyroscope",
        "litellm",
    )
    return dict(zip(keys, results, strict=True))


def _merge_homelab_checks(
    checks: dict[str, Any],
    rows: list[tuple[str, str, str, str | None]],
    results: list[dict[str, Any]],
) -> None:
    """Merge homelab HTTP probes into the stable ``checks`` mapping."""
    for (key, url, display_label, icon_src), result in zip(
        rows,
        results,
        strict=True,
    ):
        normalized = _normalize_probe_result_errors(result)
        row: dict[str, Any] = {
            **normalized,
            "display_label": display_label,
            "name": display_label,
            "href": url,
            "tunnel_url": url,
            "tls_trusted": _tls_trusted_from_https_probe_result(normalized, url),
        }
        if icon_src:
            row["icon_src"] = icon_src
        checks[key] = row


async def build_healthz_payload(
    request: Request,
    *,
    redis_client: Any,
    engine: Engine,
) -> dict[str, Any]:
    """Build the deep dependency-health payload used by ``/healthz``."""
    base = await fetch_base_health(request)
    homelab_rows = await homelab_healthz_probe_rows()
    dependency_results, homelab_results = await asyncio.gather(
        _run_dependency_probes(redis_client, engine),
        asyncio.gather(
            *(
                probe_https_get_reachable(url, probe_name=display_label)
                for _, url, display_label, _ in homelab_rows
            ),
        ),
    )
    checks = _dependency_checks(dependency_results)
    _merge_homelab_checks(checks, homelab_rows, homelab_results)
    checks = {
        name: _normalize_probe_result_errors(check)
        for name, check in checks.items()
    }
    await enrich_integration_metadata(checks)
    return {**base, "checks": checks, "version": request.app.version}
