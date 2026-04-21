"""Dependency probes for the extended ``/healthz`` endpoint."""

from __future__ import annotations

import asyncio
import socket
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.engine import Engine

from nabla.api.auth.openstack import probe_ovh_me_reachable
from nabla.config_settings import (
    DD_AGENT_HOST,
    DD_TRACE_AGENT_PORT,
    PYROSCOPE_ENDPOINT,
    REDIS_URL,
    SENTRY_DSN,
    UNLEASH_API_URL,
    UNLEASH_APP_NAME,
    UNLEASH_INSTANCE_ID,
    _unleash_requests_kwargs,
    get_openid_config,
    get_settings,
)
from nabla.integrations.brave_search import _BRAVE_WEB_SEARCH_URL
from nabla.integrations.google_programmable_search import _GOOGLE_CSE_URL
from nabla.integrations.appwrite_client import appwrite_health
from nabla.integrations.tavily_search import get_tavily_client


def _normalize_probe_error(message: str) -> str:
    """Collapse noisy HTML (e.g. Cloudflare Tunnel error pages) to a short label."""
    if "cloudflare tunnel error" in message.lower():
        return "Cloudflare Tunnel error"
    return message[:500]


def _normalize_probe_result_errors(result: dict[str, Any]) -> dict[str, Any]:
    """Apply :func:`_normalize_probe_error` to a ``result`` dict's ``error`` field if present."""
    err = result.get("error")
    if isinstance(err, str):
        return {**result, "error": _normalize_probe_error(err)}
    return result


async def fetch_base_health(request: Request) -> dict[str, Any]:
    """GET ``/health`` on this app (same scheme/host/port as the incoming request)."""
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
        return {"status": "health_unexpected_shape", "http_status": response.status_code}
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
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"reachable": True}
    except Exception as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}


async def check_supabase_http() -> dict[str, Any]:
    settings = get_settings()
    base_url = (settings.supabase_url or "").strip()
    if not base_url:
        return {
            "reachable": None,
            "skipped": True,
            "reason": "SUPABASE_URL not configured",
        }
    health_url = f"{base_url.rstrip('/')}/auth/v1/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(health_url)
    except httpx.HTTPError as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}
    return {
        "reachable": response.status_code < 500,
        "http_status": response.status_code,
    }


def probe_tavily_search() -> dict[str, Any]:
    client = get_tavily_client()
    if client is None:
        return {
            "reachable": None,
            "skipped": True,
            "reason": "TAVILY_API_KEY not configured",
        }
    try:
        client.search(".", search_depth="basic", max_results=1, timeout=5.0)
    except Exception as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}
    return {"reachable": True}


def probe_brave_search() -> dict[str, Any]:
    settings = get_settings()
    if settings.brave_api_key is None:
        return {
            "reachable": None,
            "skipped": True,
            "reason": "BRAVE_API_KEY not configured",
        }
    key = settings.brave_api_key.get_secret_value().strip()
    if not key:
        return {
            "reachable": None,
            "skipped": True,
            "reason": "BRAVE_API_KEY not configured",
        }
    try:
        with httpx.Client(timeout=5.0) as http_client:
            response = http_client.get(
                _BRAVE_WEB_SEARCH_URL,
                params={"q": ".", "count": 1},
                headers={"X-Subscription-Token": key, "Accept": "application/json"},
            )
    except Exception as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}
    return {"reachable": response.status_code < 500, "http_status": response.status_code}


def probe_google_cse() -> dict[str, Any]:
    settings = get_settings()
    if settings.google_search_api_key is None:
        return {
            "reachable": None,
            "skipped": True,
            "reason": "GOOGLE_SEARCH_API_KEY not configured",
        }
    gkey = settings.google_search_api_key.get_secret_value().strip()
    if not gkey:
        return {
            "reachable": None,
            "skipped": True,
            "reason": "GOOGLE_SEARCH_API_KEY not configured",
        }
    cx = (settings.google_search_cx or "").strip()
    if not cx:
        return {
            "reachable": None,
            "skipped": True,
            "reason": "Google CSE id (cx) not configured",
        }
    try:
        with httpx.Client(timeout=5.0) as http_client:
            response = http_client.get(
                _GOOGLE_CSE_URL,
                params={"key": gkey, "cx": cx, "q": ".", "num": 1},
            )
    except Exception as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}
    return {"reachable": response.status_code < 500, "http_status": response.status_code}


def probe_appwrite_health() -> dict[str, Any]:
    try:
        appwrite_health()
    except RuntimeError as exc:
        message = str(exc)
        if "must be configured" in message or "not installed" in message:
            return {
                "reachable": None,
                "skipped": True,
                "reason": message,
            }
        return {"reachable": False, "error": _normalize_probe_error(message)}
    except Exception as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}
    return {"reachable": True}


def probe_keycloak_well_known() -> dict[str, Any]:
    try:
        cfg = get_openid_config()
    except Exception as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}
    if isinstance(cfg, dict) and cfg.get("issuer"):
        return {"reachable": True}
    if "cloudflare tunnel error" in str(cfg).lower():
        return {"reachable": False, "error": _normalize_probe_error(str(cfg))}
    return {
        "reachable": False,
        "error": _normalize_probe_error("unexpected OpenID well-known response"),
    }


def probe_unleash_client_features() -> dict[str, Any]:
    base_url = UNLEASH_API_URL.rstrip("/")
    url = f"{base_url}/client/features"
    verify = _unleash_requests_kwargs().get("verify", True)
    try:
        with httpx.Client(timeout=10.0, verify=verify) as http_client:
            response = http_client.get(
                url,
                headers={
                    "UNLEASH-APPNAME": UNLEASH_APP_NAME,
                    "UNLEASH-INSTANCEID": UNLEASH_INSTANCE_ID,
                },
            )
    except Exception as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}
    return {"reachable": response.status_code < 500, "http_status": response.status_code}


def probe_sentry_ingest_host() -> dict[str, Any]:
    dsn = (SENTRY_DSN or "").strip()
    if not dsn:
        return {
            "reachable": None,
            "skipped": True,
            "reason": "SENTRY_DSN not configured",
        }
    parsed = urlparse(dsn)
    if not parsed.scheme or not parsed.hostname:
        return {"reachable": False, "error": _normalize_probe_error("invalid SENTRY_DSN")}
    try:
        with httpx.Client(timeout=5.0, follow_redirects=True) as http_client:
            response = http_client.get(f"{parsed.scheme}://{parsed.hostname}/")
    except Exception as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}
    return {"reachable": response.status_code < 500, "http_status": response.status_code}


def probe_datadog_trace_agent() -> dict[str, Any]:
    try:
        with socket.create_connection(
            (DD_AGENT_HOST, int(DD_TRACE_AGENT_PORT)),
            timeout=3.0,
        ) as sock:
            sock.close()
    except OSError as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}
    return {"reachable": True, "host": DD_AGENT_HOST, "port": int(DD_TRACE_AGENT_PORT)}


def probe_pyroscope_server() -> dict[str, Any]:
    base = (PYROSCOPE_ENDPOINT or "").strip().rstrip("/")
    if not base:
        return {
            "reachable": None,
            "skipped": True,
            "reason": "PYROSCOPE_ENDPOINT not configured",
        }
    last_error = ""
    for path in ("/ready", "/health", "/"):
        try:
            with httpx.Client(timeout=3.0) as http_client:
                response = http_client.get(f"{base}{path}")
        except httpx.HTTPError as exc:
            last_error = _normalize_probe_error(str(exc))
            continue
        except Exception as exc:
            return {"reachable": False, "error": _normalize_probe_error(str(exc))}
        if response.status_code < 500:
            return {
                "reachable": True,
                "http_status": response.status_code,
                "path": path,
            }
        last_error = f"http_status={response.status_code}"
    return {
        "reachable": False,
        "error": _normalize_probe_error(last_error or "no response"),
    }


async def build_healthz_payload(request: Request, *, redis_client: Any, engine: Engine) -> dict[str, Any]:
    base = await fetch_base_health(request)
    (
        redis_check,
        postgres_check,
        supabase_check,
        ovh_check,
        tavily_check,
        brave_check,
        google_check,
        appwrite_check,
        keycloak_check,
        unleash_check,
        sentry_check,
        datadog_check,
        pyroscope_check,
    ) = await asyncio.gather(
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
        run_in_threadpool(probe_sentry_ingest_host),
        run_in_threadpool(probe_datadog_trace_agent),
        run_in_threadpool(probe_pyroscope_server),
    )
    checks = {
        "redis": redis_check,
        "postgres": postgres_check,
        "supabase": supabase_check,
        "openstack_me": ovh_check,
        "tavily": tavily_check,
        "brave": brave_check,
        "google": google_check,
        "appwrite": appwrite_check,
        "keycloak": keycloak_check,
        "unleash": unleash_check,
        "sentry": sentry_check,
        "datadog": datadog_check,
        "pyroscope": pyroscope_check,
    }
    checks = {name: _normalize_probe_result_errors(ch) for name, ch in checks.items()}
    return {**base, "checks": checks, "version": request.app.version}
