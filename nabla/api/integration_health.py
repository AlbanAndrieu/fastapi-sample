"""Health probes for optional external integrations used by ``/healthz``."""

from __future__ import annotations

import socket
from typing import Any

import httpx

from nabla.api.health_probe_utils import (
    normalize_probe_error as _normalize_probe_error,
    probe_https_tls_trusted,
)
from nabla.config_settings import (
    DD_AGENT_HOST,
    DD_TRACE_AGENT_PORT,
    DD_TRACE_AGENT_URL,
    PYROSCOPE_ENDPOINT,
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
    api_key = settings.google_search_api_key.get_secret_value().strip()
    if not api_key:
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
                params={"key": api_key, "cx": cx, "q": ".", "num": 1},
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
        config = get_openid_config()
    except Exception as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}
    if isinstance(config, dict) and config.get("issuer"):
        return {"reachable": True}
    if "cloudflare tunnel error" in str(config).lower():
        return {"reachable": False, "error": _normalize_probe_error(str(config))}
    return {
        "reachable": False,
        "error": _normalize_probe_error("unexpected OpenID well-known response"),
    }


def probe_unleash_client_features() -> dict[str, Any]:
    url = f"{UNLEASH_API_URL.rstrip('/')}/client/features"
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
            with httpx.Client(timeout=5.0, follow_redirects=True) as http_client:
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
        url = f"{base}{path}"
        try:
            with httpx.Client(timeout=3.0) as http_client:
                response = http_client.get(url)
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
                "url": url,
            }
        last_error = f"http_status={response.status_code}"
    return {
        "reachable": False,
        "error": _normalize_probe_error(last_error or "no response"),
    }


async def enrich_integration_metadata(checks: dict[str, Any]) -> None:
    """Attach display URLs and trusted-TLS metadata to integration results."""
    await _enrich_litellm(checks)
    await _enrich_pyroscope(checks)


async def _enrich_litellm(checks: dict[str, Any]) -> None:
    result = checks.get("litellm")
    if not isinstance(result, dict) or result.get("skipped"):
        return
    settings = get_settings()
    base = (settings.litellm_healthz_url or "").strip().rstrip("/")
    probe_url = str(result.get("url") or "").strip()
    if not probe_url and base:
        probe_url = f"{base}/health"
    href = ""
    if probe_url.lower().startswith(("http://", "https://")):
        href = probe_url
    elif base:
        href = base if "://" in base else f"https://{base}"
        if not href.endswith("/"):
            href += "/"
    output: dict[str, Any] = {**result, "display_label": "LiteLLM"}
    if href:
        output["href"] = href
        output["tls_trusted"] = (
            await probe_https_tls_trusted(href)
            if href.lower().startswith("https:")
            else None
        )
    checks["litellm"] = output


async def _enrich_pyroscope(checks: dict[str, Any]) -> None:
    result = checks.get("pyroscope")
    if (
        not isinstance(result, dict)
        or result.get("skipped")
        or not str(result.get("url") or "").strip()
    ):
        return
    url = str(result["url"]).strip()
    checks["pyroscope"] = {
        **result,
        "display_label": "Pyroscope",
        "href": url,
        "tls_trusted": (
            await probe_https_tls_trusted(url)
            if url.lower().startswith("https:")
            else None
        ),
    }
