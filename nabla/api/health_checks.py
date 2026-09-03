"""Core dependency probes and orchestration for the extended ``/healthz`` endpoint."""

from __future__ import annotations

import asyncio
import logging
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
from nabla.api.probe_budget import ProbeBudget
from nabla.config_settings import REDIS_URL, get_settings

logger = logging.getLogger(__name__)

_HEALTHZ_PROBE_DEADLINE_SEC = 8.0
_HEALTHZ_MAX_CONCURRENCY = 4
_DEPENDENCY_KEYS = (
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


def _http_probe_error_kind(exc: Exception) -> str:
    """Classify outbound HTTP failures without exposing implementation details."""
    message = str(exc).lower()
    if isinstance(exc, httpx.ConnectTimeout):
        return "connect_timeout"
    if isinstance(exc, httpx.ReadTimeout):
        return "read_timeout"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if any(marker in message for marker in ("certificate", "ssl", "tls")):
        return "tls_error"
    if any(marker in message for marker in ("name or service not known", "nodename nor servname", "temporary failure in name resolution", "getaddrinfo")):
        return "dns_error"
    if isinstance(exc, httpx.ConnectError):
        return "connect_error"
    if isinstance(exc, httpx.HTTPError):
        return "http_error"
    if isinstance(exc, OSError):
        return "os_error"
    return "unknown_error"


async def probe_https_get_reachable(
    url: str,
    *,
    probe_name: str | None = None,
) -> dict[str, Any]:
    """GET ``url``; any completed HTTP response counts as reachable."""
    started = time.monotonic()
    logger.debug("health outbound probe started name=%s url=%s", probe_name or "-", url)
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
        elapsed_ms = round((time.monotonic() - started) * 1000)
        error_kind = _http_probe_error_kind(exc)
        exception_type = type(exc).__name__
        normalized_error = _normalize_probe_error(str(exc))
        logger.warning(
            "health outbound probe failed name=%s url=%s error_kind=%s exception_type=%s elapsed_ms=%s error=%s",
            probe_name or "-",
            url,
            error_kind,
            exception_type,
            elapsed_ms,
            normalized_error,
        )
        return {
            "reachable": False,
            "error": normalized_error,
            "error_kind": error_kind,
            "exception_type": exception_type,
            "elapsed_ms": elapsed_ms,
            "url": url,
        }
    elapsed_ms = round((time.monotonic() - started) * 1000)
    logger.debug(
        "health outbound probe completed name=%s url=%s http_status=%s elapsed_ms=%s",
        probe_name or "-",
        url,
        response.status_code,
        elapsed_ms,
    )
    return {
        "reachable": True,
        "http_status": response.status_code,
        "elapsed_ms": elapsed_ms,
        "url": url,
    }


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


async def fetch_base_health(_request: Request) -> dict[str, Any]:
    """Build the lightweight local health payload without a self-HTTP round trip."""
    try:
        from nabla.api.demo.sensor import health_check  # noqa: PLC0415

        body = await health_check()
    except Exception as exc:
        return {
            "status": "health_fetch_failed",
            "error": _normalize_probe_error(str(exc)),
        }
    if not isinstance(body, dict):
        return {
            "status": "health_unexpected_shape",
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
            "reason": ("SUPABASE_PUBLISHABLE_KEY and SUPABASE_SERVICE_ROLE_KEY are not configured"),
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


def _deadline_probe_result(
    probe_name: str,
    *,
    url: str | None = None,
) -> dict[str, Any]:
    """Return explicit unknown/failure evidence when the aggregate budget expires."""
    result: dict[str, Any] = {
        "reachable": False,
        "timed_out": True,
        "error": "aggregate health probe deadline exceeded",
        "error_kind": "deadline",
        "probe": probe_name,
    }
    if url:
        result["url"] = url
    return result


async def _run_dependency_probes(
    redis_client: Any,
    engine: Engine,
    budget: ProbeBudget,
) -> tuple[dict[str, Any], ...]:
    """Run dependency probes through one shared concurrency/deadline budget."""
    factories = (
        lambda: check_redis_ping(redis_client),
        lambda: run_in_threadpool(check_postgres_sql, engine),
        check_supabase_http,
        lambda: run_in_threadpool(probe_ovh_me_reachable),
        lambda: run_in_threadpool(probe_tavily_search),
        lambda: run_in_threadpool(probe_brave_search),
        lambda: run_in_threadpool(probe_google_cse),
        lambda: run_in_threadpool(probe_appwrite_health),
        lambda: run_in_threadpool(probe_keycloak_well_known),
        lambda: run_in_threadpool(probe_unleash_client_features),
        lambda: run_in_threadpool(probe_sentry_reachable),
        lambda: run_in_threadpool(probe_datadog_trace_agent),
        lambda: run_in_threadpool(probe_pyroscope_server),
        lambda: run_in_threadpool(probe_litellm_public_proxy),
    )
    results = await asyncio.gather(
        *(
            budget.run(
                factory,
                timeout_value=lambda name=name: _deadline_probe_result(name),
            )
            for name, factory in zip(_DEPENDENCY_KEYS, factories, strict=True)
        ),
    )
    return tuple(results)


def _dependency_checks(results: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    """Map dependency probe results to the stable public check keys."""
    return dict(zip(_DEPENDENCY_KEYS, results, strict=True))


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
    budget = ProbeBudget(
        deadline_seconds=_HEALTHZ_PROBE_DEADLINE_SEC,
        max_concurrency=_HEALTHZ_MAX_CONCURRENCY,
    )
    homelab_rows = await budget.run(
        homelab_healthz_probe_rows,
        timeout_value=lambda: None,
    )
    catalog_timed_out = homelab_rows is None
    rows = homelab_rows or []

    dependency_results, homelab_results = await asyncio.gather(
        _run_dependency_probes(redis_client, engine, budget),
        asyncio.gather(
            *(
                budget.run(
                    lambda url=url, display_label=display_label: probe_https_get_reachable(
                        url,
                        probe_name=display_label,
                    ),
                    timeout_value=lambda display_label=display_label, url=url: _deadline_probe_result(
                        display_label,
                        url=url,
                    ),
                )
                for _, url, display_label, _ in rows
            ),
        ),
    )
    checks = _dependency_checks(dependency_results)
    _merge_homelab_checks(checks, rows, list(homelab_results))
    if catalog_timed_out:
        checks["homelab_catalog"] = _deadline_probe_result("homelab_catalog")
    checks = {name: _normalize_probe_result_errors(check) for name, check in checks.items()}
    await budget.run(
        lambda: enrich_integration_metadata(checks),
        timeout_value=lambda: None,
    )
    return {
        **base,
        "checks": checks,
        "version": request.app.version,
        "probe_budget": {
            "deadline_seconds": _HEALTHZ_PROBE_DEADLINE_SEC,
            "max_concurrency": _HEALTHZ_MAX_CONCURRENCY,
        },
    }
