"""Dependency probes for the extended ``/healthz`` endpoint."""

from __future__ import annotations

import asyncio
import socket
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
    probe_https_tls_trusted,
)
from nabla.api.homelab_catalog import homelab_healthz_probe_rows
from nabla.config_settings import (
    DD_AGENT_HOST,
    DD_TRACE_AGENT_PORT,
    DD_TRACE_AGENT_URL,
    PYROSCOPE_ENDPOINT,
    REDIS_URL,
    UNLEASH_API_URL,
    UNLEASH_APP_NAME,
    UNLEASH_INSTANCE_ID,
    _unleash_requests_kwargs,
    _unleash_timeout_s,
    get_openid_config,
    get_settings,
)
from nabla.integrations.appwrite_client import appwrite_health
from nabla.integrations.brave_search import _BRAVE_WEB_SEARCH_URL
from nabla.integrations.google_search import _GOOGLE_CSE_URL
from nabla.integrations.tavily_search import get_tavily_client
from nabla.utils.sentry_config import select_sentry_dsn, sentry_dsn_is_reachable


async def probe_https_get_reachable(url: str) -> dict[str, Any]:
    """GET ``url``; any completed HTTP response counts as reachable."""
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
        return {
            "reachable": False,
            "error": _normalize_probe_error(str(exc)),
            "url": url,
        }
    return {"reachable": True, "http_status": response.status_code, "url": url}


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
    err = str(result.get("error") or "").lower()
    if any(
        marker in err
        for marker in ("ssl", "certificate", "tls", "cert verify", "hostname mismatch")
    ):
        return False
    return None


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
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
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
                headers={
                    "X-Subscription-Token": key,
                    "Accept": "application/json",
                },
            )
    except Exception as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}
    return {
        "reachable": response.status_code < 500,
        "http_status": response.status_code,
    }


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
    return {
        "reachable": response.status_code < 500,
        "http_status": response.status_code,
    }


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
        with httpx.Client(
            timeout=float(_unleash_timeout_s),
            verify=verify,
        ) as http_client:
            response = http_client.get(
                url,
                headers={
                    "UNLEASH-APPNAME": UNLEASH_APP_NAME,
                    "UNLEASH-INSTANCEID": UNLEASH_INSTANCE_ID,
                },
            )
    except Exception as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}
    return {
        "reachable": response.status_code < 500,
        "http_status": response.status_code,
    }


def probe_sentry_reachable() -> dict[str, Any]:
    """Check the selected Sentry intake without generating an error event."""
    dsn, target = select_sentry_dsn()
    if not dsn:
        return {
            "reachable": None,
            "skipped": True,
            "reason": "SENTRY_LOCAL_DSN and SENTRY_DSN are not configured",
        }
    return {
        "reachable": sentry_dsn_is_reachable(dsn),
        "target": target,
        "probe": "dsn_socket",
    }


def probe_datadog_trace_agent() -> dict[str, Any]:
    if not (DD_TRACE_AGENT_URL or "").strip():
        return {
            "reachable": None,
            "skipped": True,
            "reason": "DD_TRACE_AGENT_URL is not configured",
        }
    try:
        with socket.create_connection(
            (DD_AGENT_HOST, int(DD_TRACE_AGENT_PORT)),
            timeout=3.0,
        ) as sock:
            sock.close()
    except OSError as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}
    return {
        "reachable": True,
        "host": DD_AGENT_HOST,
        "port": int(DD_TRACE_AGENT_PORT),
    }


def probe_litellm_public_proxy() -> dict[str, Any]:
    """GET LiteLLM liveness; fall back to readiness then generic health."""
    settings = get_settings()
    base = (settings.litellm_healthz_url or "").strip().rstrip("/")
    if not base:
        return {
            "reachable": None,
            "skipped": True,
            "reason": "LITELLM_HEALTHZ_URL empty (litellm probe disabled)",
        }
    last_error = ""
    for path in ("/health/liveliness", "/health/readiness", "/health"):
        url = f"{base}{path}"
        try:
            with httpx.Client(
                timeout=5.0,
                follow_redirects=True,
            ) as http_client:
                response = http_client.get(url)
        except httpx.HTTPError as exc:
            last_error = _normalize_probe_error(str(exc))
            continue
        except Exception as exc:
            return {"reachable": False, "error": _normalize_probe_error(str(exc))}
        if response.is_success:
            return {
                "reachable": True,
                "http_status": response.status_code,
                "path": path,
                "url": url,
            }
        last_error = f"http_status={response.status_code}"
    return {
        "reachable": False,
        "error": _normalize_probe_error(last_error or "no response"),
        "base": base,
    }


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
                "url": f"{base}{path}",
            }
        last_error = f"http_status={response.status_code}"
    return {
        "reachable": False,
        "error": _normalize_probe_error(last_error or "no response"),
    }


async def _healthz_enrich_litellm(checks: dict[str, Any]) -> None:
    lit = checks.get("litellm")
    if not isinstance(lit, dict) or lit.get("skipped"):
        return
    settings = get_settings()
    base = (settings.litellm_healthz_url or "").strip().rstrip("/")
    probe_url = (lit.get("url") or "").strip()
    if not probe_url and base:
        probe_url = f"{base}/health"
    href_lit = ""
    if probe_url.lower().startswith(("http://", "https://")):
        href_lit = probe_url
    elif base:
        href_lit = base if "://" in base else f"https://{base}"
        if not href_lit.endswith("/"):
            href_lit += "/"
    tls_lit: bool | None = None
    if href_lit:
        if href_lit.lower().startswith("https:"):
            tls_lit = await probe_https_tls_trusted(href_lit)
        else:
            tls_lit = _tls_trusted_from_https_probe_result(lit, href_lit)
    lit_out: dict[str, Any] = {**lit, "display_label": "LiteLLM"}
    if href_lit:
        lit_out["href"] = href_lit
        lit_out["tls_trusted"] = tls_lit
    checks["litellm"] = lit_out


async def _healthz_enrich_pyroscope(checks: dict[str, Any]) -> None:
    pyr = checks.get("pyroscope")
    if (
        not isinstance(pyr, dict)
        or pyr.get("skipped")
        or not (pyr.get("url") or "").strip()
    ):
        return
    purl = str(pyr["url"]).strip()
    if purl.lower().startswith("https:"):
        checks["pyroscope"] = {
            **pyr,
            "display_label": "Pyroscope",
            "href": purl,
            "tls_trusted": await probe_https_tls_trusted(purl),
        }
    else:
        checks["pyroscope"] = {
            **pyr,
            "display_label": "Pyroscope",
            "href": purl,
            "tls_trusted": None,
        }


async def build_healthz_payload(
    request: Request,
    *,
    redis_client: Any,
    engine: Engine,
) -> dict[str, Any]:
    """Build the deep dependency-health payload used by ``/healthz``."""
    base = await fetch_base_health(request)
    homelab_rows = await homelab_healthz_probe_rows()
    (
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
            litellm_check,
        ),
        albandrieu_results,
    ) = await asyncio.gather(
        asyncio.gather(
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
        ),
        asyncio.gather(
            *(
                probe_https_get_reachable(url)
                for _, url, _, _ in homelab_rows
            ),
        ),
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
        "litellm": litellm_check,
    }
    for (key, url, display_label, icon_src), res in zip(
        homelab_rows,
        albandrieu_results,
        strict=True,
    ):
        norm = _normalize_probe_result_errors(res)
        row: dict[str, Any] = {
            **norm,
            "display_label": display_label,
            "name": display_label,
            "href": url,
            "tunnel_url": url,
            "tls_trusted": _tls_trusted_from_https_probe_result(norm, url),
        }
        if icon_src:
            row["icon_src"] = icon_src
        checks[key] = row
    checks = {
        name: _normalize_probe_result_errors(check)
        for name, check in checks.items()
    }

    await _healthz_enrich_litellm(checks)
    await _healthz_enrich_pyroscope(checks)
    return {**base, "checks": checks, "version": request.app.version}
