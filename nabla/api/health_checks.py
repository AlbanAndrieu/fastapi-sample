"""Dependency probes for the extended ``/healthz`` endpoint."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import socket
import ssl
from typing import Any
from urllib.parse import urlparse

import httpx
import urllib3
from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.engine import Engine

from nabla.api.auth.openstack import probe_ovh_me_reachable
from nabla.api.homelab_catalog import (
    homelab_healthz_probe_rows,
    homelab_sickz_catalog_for_sickz,
)
from nabla.config_settings import (
    _ALBANDRIEU_PUBLIC_DOMAIN_SUFFIX,
    APP_DOMAIN,
    DD_AGENT_HOST,
    DD_TRACE_AGENT_PORT,
    DD_TRACE_AGENT_URL,
    PYROSCOPE_ENDPOINT,
    REDIS_URL,
    UNLEASH_API_URL,
    UNLEASH_APP_NAME,
    UNLEASH_INSTANCE_ID,
    APIDeploymentSettings,
    _default_sickz_targets_value,
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

_log = logging.getLogger(__name__)


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


async def probe_https_get_reachable(url: str) -> dict[str, Any]:
    """GET ``url``; any completed HTTP response counts as reachable (host + TLS + server spoke)."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0), follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "nabla-healthz-probe/1.0"})
    except httpx.HTTPError as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc)), "url": url}
    except OSError as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc)), "url": url}
    return {"reachable": True, "http_status": response.status_code, "url": url}


def _tls_trusted_from_https_probe_result(result: dict[str, Any], url: str) -> bool | None:
    """Infer CA-trusted TLS from a probe made with ``verify=True`` (httpx default)."""
    if not (url or "").strip().lower().startswith("https:"):
        return None
    if result.get("skipped"):
        return None
    if result.get("reachable") is True:
        return True
    err = str(result.get("error") or "").lower()
    if any(x in err for x in ("ssl", "certificate", "tls", "cert verify", "hostname mismatch")):
        return False
    return None


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
    headers: dict[str, str] = {}
    if settings.supabase_service_role_key is not None:
        api_key = settings.supabase_service_role_key.get_secret_value().strip()
        if api_key:
            headers = {"apikey": api_key, "Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(health_url, headers=headers)
    except httpx.HTTPError as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}
    return {
        "reachable": response.status_code < 400,
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
        with httpx.Client(timeout=float(_unleash_timeout_s), verify=verify) as http_client:
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
    return {"reachable": True, "host": DD_AGENT_HOST, "port": int(DD_TRACE_AGENT_PORT)}


def probe_litellm_public_proxy() -> dict[str, Any]:
    """GET LiteLLM proxy liveness (unauthenticated); falls back to readiness if needed."""
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
            tls_lit = await _probe_sickz_tls_trusted(href_lit)
        else:
            tls_lit = _tls_trusted_from_https_probe_result(lit, href_lit)
    lit_out: dict[str, Any] = {**lit, "display_label": "LiteLLM"}
    if href_lit:
        lit_out["href"] = href_lit
        lit_out["tls_trusted"] = tls_lit
    checks["litellm"] = lit_out


async def _healthz_enrich_pyroscope(checks: dict[str, Any]) -> None:
    pyr = checks.get("pyroscope")
    if not isinstance(pyr, dict) or pyr.get("skipped") or not (pyr.get("url") or "").strip():
        return
    purl = str(pyr["url"]).strip()
    if purl.lower().startswith("https:"):
        checks["pyroscope"] = {
            **pyr,
            "display_label": "Pyroscope",
            "href": purl,
            "tls_trusted": await _probe_sickz_tls_trusted(purl),
        }
    else:
        checks["pyroscope"] = {
            **pyr,
            "display_label": "Pyroscope",
            "href": purl,
            "tls_trusted": None,
        }


async def build_healthz_payload(request: Request, *, redis_client: Any, engine: Engine) -> dict[str, Any]:
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
        asyncio.gather(*(probe_https_get_reachable(url) for _, url, _, _ in homelab_rows)),
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
    for (key, url, display_label, icon_src), res in zip(homelab_rows, albandrieu_results, strict=True):
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
    checks = {name: _normalize_probe_result_errors(ch) for name, ch in checks.items()}

    await _healthz_enrich_litellm(checks)
    await _healthz_enrich_pyroscope(checks)
    return {**base, "checks": checks, "version": request.app.version}


def _parse_sickz_target_groups(raw: str) -> list[list[str]]:
    """Split ``SICKZ_TARGETS`` into groups; ``|`` joins equivalent URLs (same logical target)."""
    text = (raw or "").replace("\n", ",")
    groups: list[list[str]] = []
    for segment in text.split(","):
        seg = segment.strip()
        if not seg:
            continue
        aliases = [a.strip() for a in seg.split("|") if a.strip()]
        if aliases:
            groups.append(aliases)
    return groups


def _normalize_sickz_targets_for_compare(raw: str) -> str:
    parts: list[str] = []
    for segment in (raw or "").replace("\n", ",").split(","):
        s = segment.strip()
        if s:
            parts.append(s)
    return ",".join(parts)


def _sickz_targets_equal_default_catalog_mode(raw: str) -> bool:
    """True when ``SICKZ_TARGETS`` is still the pfSense-only default (homelab JSON URLs are merged in)."""
    return _normalize_sickz_targets_for_compare(raw) == _normalize_sickz_targets_for_compare(
        _default_sickz_targets_value(),
    )


_ALBANDRIEU_COM = f".{_ALBANDRIEU_PUBLIC_DOMAIN_SUFFIX}"
_SICKZ_ICON_FILENAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*\.svg\Z", re.IGNORECASE)


def _sickz_validate_icon_filename(name: str) -> str:
    n = name.strip()
    if _SICKZ_ICON_FILENAME_RE.match(n):
        return n
    return "homepage.svg"


def _sickz_ipv4_host(host: str) -> bool:
    parts = host.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


def _sickz_short_label_for_url(url: str) -> str:
    """Host (+ optional nonstandard port) without scheme; strip ``*.albandrieu.com`` suffix."""
    raw = url.strip()
    p = urlparse(raw)
    host = (p.hostname or "").strip().lower()
    port = p.port
    if not host:
        tail = re.sub(r"^https?://", "", raw, flags=re.I)
        return (tail[:48] + "…") if len(tail) > 48 else tail
    display = host.removesuffix(_ALBANDRIEU_COM)
    if port and port not in (80, 443):
        return f"{display}:{port}"
    return display


def _sickz_display_label(urls: list[str]) -> str:
    if not urls:
        return "target"
    return " · ".join(_sickz_short_label_for_url(u) for u in urls)


def _sickz_row_href(urls: list[str]) -> str:
    return urls[0].strip() if urls else ""


# When :func:`_sickz_pfsense_canonical_href` applies, :func:`_probe_sickz_alias_group` also TCP-checks
# these ports on the canonical host (``home.albandrieu.com``).
_SICKZ_PFSENSE_EXTRA_TCP_PORTS: tuple[int, ...] = (
    22,
    9922,
    8076,
    7000,
    8200,
    9000,
    3000,
    4100,
    1194,
    1195,
    8080,
    8081,
    8091,
)


def _sickz_pfsense_canonical_href(urls: list[str]) -> str | None:
    """pfSense sickz group: label ``PfSense``, link ``https://home.albandrieu.com:10443/`` (not the Docker bridge alias).

    When this returns a URL, sickz also probes :data:`_SICKZ_PFSENSE_EXTRA_TCP_PORTS` on the canonical
    hostname (see :func:`_sickz_pfsense_canonical_tcp_host`).
    """
    hosts: set[str] = set()
    for raw in urls:
        p = urlparse(raw.strip())
        if p.port != 10443:
            continue
        hosts.add((p.hostname or "").lower())
    if not hosts:
        return None
    if "home.albandrieu.com" in hosts or "172.17.0.1" in hosts:
        return "https://home.albandrieu.com:10443/"
    return None


def _sickz_pfsense_canonical_tcp_host(urls: list[str]) -> str | None:
    """Hostname for extra TCP probes when :func:`_sickz_pfsense_canonical_href` matches."""
    href = _sickz_pfsense_canonical_href(urls)
    if not href:
        return None
    host = (urlparse(href).hostname or "").strip().lower()
    return host or None


def _canonical_pfsense_sickz_alias_urls() -> list[str]:
    """Default pfSense sickz aliases (same first segment as :func:`_default_sickz_targets_value`)."""
    raw = _default_sickz_targets_value()
    first_segment = raw.replace("\n", ",").split(",")[0].strip()
    aliases = [a.strip() for a in first_segment.split("|") if a.strip()]
    if aliases and _sickz_pfsense_canonical_href(aliases) is not None:
        return aliases
    return [
        "https://home.albandrieu.com:10443/",
        "https://172.17.0.1:10443/",
        "http://172.17.0.1:8076/",
    ]


def _sickz_groups_include_pfsense(groups: list[list[str]]) -> bool:
    return any(_sickz_pfsense_canonical_href(g) is not None for g in groups)


def _ensure_pfsense_sickz_group(groups: list[list[str]]) -> list[list[str]]:
    """Always keep a PfSense row for ``/sickz`` and the ``/api`` board, regardless of env overrides."""
    if _sickz_groups_include_pfsense(groups):
        return groups
    return [_canonical_pfsense_sickz_alias_urls(), *groups]


def _sickz_pfsense_tcp_skip_payload(urls: list[str]) -> dict[str, Any]:
    """LAN-skip rows: include TCP port map with ``None`` so UIs can still list PfSense ports."""
    if not _sickz_pfsense_canonical_tcp_host(urls):
        return {}
    return {
        "pfsense_tcp_ports": {str(p): None for p in _SICKZ_PFSENSE_EXTRA_TCP_PORTS},
        "pfsense_tcp_ports_skipped": True,
    }


async def _probe_sickz_tcp_port_open(host: str, port: int, *, timeout_s: float = 2.0) -> bool:
    """Return whether a TCP connect to ``host:port`` completes within ``timeout_s``."""
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout_s,
        )
    except (TimeoutError, OSError, ConnectionError):
        return False
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass
    return True


def _sickz_canonical_https_tunnel_key(url: str) -> str:
    u = url.strip()
    if not u.lower().startswith("https://"):
        return u
    return u.rstrip("/") + "/"


def _sickz_homelab_icon_src_for_urls(
    urls: list[str],
    homelab_icon_by_tunnel: dict[str, str] | None,
) -> str | None:
    if not homelab_icon_by_tunnel:
        return None
    for raw in urls:
        key = _sickz_canonical_https_tunnel_key(raw)
        hit = homelab_icon_by_tunnel.get(key)
        if hit:
            return hit
    return None


def _sickz_homelab_service_name_for_urls(
    urls: list[str],
    homelab_name_by_tunnel: dict[str, str] | None,
) -> str | None:
    if not homelab_name_by_tunnel:
        return None
    for raw in urls:
        key = _sickz_canonical_https_tunnel_key(raw)
        hit = homelab_name_by_tunnel.get(key)
        if hit:
            return hit
    return None


def _sickz_icon_filename(urls: list[str]) -> str:
    """Selfh.st SVG basename for CDN; used when homelab catalog has no ``iconSrc`` for this tunnel."""
    if not urls:
        return _sickz_validate_icon_filename("homepage.svg")
    p = urlparse(urls[0].strip())
    if p.port == 10443:
        return _sickz_validate_icon_filename("pfsense.svg")
    host = (p.hostname or "").strip().lower()
    if _sickz_ipv4_host(host):
        return _sickz_validate_icon_filename("pfsense.svg")
    return _sickz_validate_icon_filename("homepage.svg")


def _sickz_row_ui_metadata(
    urls: list[str],
    homelab_icon_by_tunnel: dict[str, str] | None = None,
    homelab_name_by_tunnel: dict[str, str] | None = None,
) -> dict[str, Any]:
    pf_href = _sickz_pfsense_canonical_href(urls)
    if pf_href is not None:
        return {
            "display_label": "PfSense",
            "name": "PfSense",
            "href": pf_href,
            "tunnel_url": pf_href,
            "icon_filename": _sickz_validate_icon_filename("pfsense.svg"),
        }
    href = _sickz_row_href(urls).strip()
    catalog_name = _sickz_homelab_service_name_for_urls(urls, homelab_name_by_tunnel)
    display = catalog_name if catalog_name else _sickz_display_label(urls)
    icon_src = _sickz_homelab_icon_src_for_urls(urls, homelab_icon_by_tunnel)
    base: dict[str, Any] = {
        "display_label": display,
        "href": href,
        "tunnel_url": href,
        "icon_filename": _sickz_icon_filename(urls),
    }
    if catalog_name:
        base["name"] = catalog_name
    if icon_src:
        base["icon_src"] = icon_src
    return base


async def _probe_sickz_tls_trusted(url: str) -> bool | None:
    """``True`` if default CA store trusts the server cert; ``False`` on TLS/cert errors; ``None`` if unknown."""
    u = url.strip()
    if not u.lower().startswith("https:"):
        return None
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0),
            verify=True,
            follow_redirects=True,
        ) as client:
            await client.get(u, headers={"User-Agent": "nabla-sickz-tls-verify/1.0"})
    except ssl.SSLError:
        return False
    except httpx.HTTPError as exc:
        if isinstance(exc.__cause__, ssl.SSLError):
            return False
        return None
    except OSError:
        return None
    else:
        return True


def _sickz_network_label(settings: APIDeploymentSettings) -> str:
    custom = (settings.sickz_network_label or "").strip()
    if custom:
        return custom
    return (APP_DOMAIN or "").strip() or "this deployment"


_KNOWN_PAAS_ENV_MARKERS: tuple[str, ...] = (
    "VERCEL",
    "AWS_EXECUTION_ENV",
    "AWS_LAMBDA_FUNCTION_NAME",
    "KUBERNETES_SERVICE_HOST",
    "FLY_APP_NAME",
    "RAILWAY_ENVIRONMENT",
    "RAILWAY_PROJECT_ID",
    "HEROKU_APP_NAME",
    "DYNO",
)


def _known_paas_runtime_detected() -> bool:
    """True on common managed platforms; sickz must not skip probes there."""
    env = os.environ
    for key in _KNOWN_PAAS_ENV_MARKERS:
        val = env.get(key)
        if val is not None and str(val).strip() != "":
            return True
    return False


def _sickz_implicit_internal_network(settings: APIDeploymentSettings) -> bool:
    """Treat as home-LAN when label or public app host matches known personal deploy profile."""
    if (settings.sickz_network_label or "").strip().lower() == "nabla":
        return True
    return (APP_DOMAIN or "").strip().lower() == "albandrieu.albandrieu.com"


def _sickz_internal_network_implicit(settings: APIDeploymentSettings) -> bool:
    """True when LAN skip is implied by label/domain, not by ``SICKZ_INTERNAL_NETWORK``."""
    if bool(settings.sickz_internal_network):
        return False
    return _sickz_implicit_internal_network(settings)


def _sickz_internal_network_inferred_from(settings: APIDeploymentSettings) -> str | None:
    if bool(settings.sickz_internal_network):
        return None
    if (settings.sickz_network_label or "").strip().lower() == "nabla":
        return "SICKZ_NETWORK_LABEL=nabla"
    if (APP_DOMAIN or "").strip().lower() == "albandrieu.albandrieu.com":
        return "APP_DOMAIN=albandrieu.albandrieu.com"
    return None


def _sickz_internal_network_effective(settings: APIDeploymentSettings) -> bool:
    """LAN skip when operator enabled it, or implicit nabla/home domain match, unless on cloud/PaaS."""
    if _known_paas_runtime_detected():
        return False
    if bool(settings.sickz_internal_network):
        return True
    return _sickz_implicit_internal_network(settings)


def _sickz_skip_detail(settings: APIDeploymentSettings) -> str:
    if bool(settings.sickz_internal_network):
        return "Sickz probes are disabled (SICKZ_INTERNAL_NETWORK). This instance is treated as running on your home LAN where pfSense may be reachable."
    if (settings.sickz_network_label or "").strip().lower() == "nabla":
        return "Sickz probes are disabled: SICKZ_NETWORK_LABEL is 'nabla', so this instance is treated as on your home LAN."

    return "Sickz probes are disabled."


def _sickz_runtime_block(settings: APIDeploymentSettings) -> dict[str, Any]:
    paas = _known_paas_runtime_detected()
    cfg = bool(settings.sickz_internal_network)
    implicit = _sickz_internal_network_implicit(settings)
    return {
        "cloud_paas_detected": paas,
        "sickz_internal_network_config": cfg,
        "sickz_internal_network_implicit": implicit,
        "internal_network_inferred_from": _sickz_internal_network_inferred_from(settings),
        "sickz_internal_network_effective": _sickz_internal_network_effective(settings),
    }


async def _probe_sickz_url(url: str) -> dict[str, Any]:
    """Return whether ``url`` responds over HTTP(S). TLS cert verification is off on purpose."""
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0),
            verify=False,  # noqa: S501 — sickz must detect TLS hosts even with invalid certs
            follow_redirects=True,
        ) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "nabla-sickz-probe/1.0"},
            )
    except httpx.HTTPError as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}
    except OSError as exc:
        return {"reachable": False, "error": _normalize_probe_error(str(exc))}
    return {"reachable": True, "http_status": response.status_code}


async def _probe_sickz_alias_group(
    urls: list[str],
    homelab_icon_by_tunnel: dict[str, str] | None = None,
    homelab_name_by_tunnel: dict[str, str] | None = None,
) -> dict[str, Any]:
    """One logical target: reachable if any alias responds."""
    href = _sickz_row_href(urls)
    tls_coro = _probe_sickz_tls_trusted(href) if href.lower().startswith("https:") else _async_none()
    pf_tcp_host = _sickz_pfsense_canonical_tcp_host(urls)
    if pf_tcp_host:
        tcp_coro = asyncio.gather(
            *(_probe_sickz_tcp_port_open(pf_tcp_host, port) for port in _SICKZ_PFSENSE_EXTRA_TCP_PORTS),
        )
        results, tls_trusted, tcp_reachable = await asyncio.gather(
            asyncio.gather(*(_probe_sickz_url(u) for u in urls)),
            tls_coro,
            tcp_coro,
        )
    else:
        results, tls_trusted = await asyncio.gather(
            asyncio.gather(*(_probe_sickz_url(u) for u in urls)),
            tls_coro,
        )
        tcp_reachable = None
    by_url = {u: _normalize_probe_result_errors(r) for u, r in zip(urls, results, strict=True)}
    any_reachable = any(r.get("reachable") is True for r in results)
    out: dict[str, Any] = {
        "reachable": any_reachable,
        "aliases_probed": urls,
        "alias_results": by_url,
        "tls_trusted": tls_trusted,
        **_sickz_row_ui_metadata(urls, homelab_icon_by_tunnel, homelab_name_by_tunnel),
    }
    if tcp_reachable is not None:
        out["pfsense_tcp_ports"] = {str(port): reachable for port, reachable in zip(_SICKZ_PFSENSE_EXTRA_TCP_PORTS, tcp_reachable, strict=True)}
    for r in results:
        if r.get("reachable") is True and r.get("http_status") is not None:
            out["http_status"] = r["http_status"]
            break
    return out


async def _async_none() -> None:
    return None


async def build_sickz_payload(request: Request) -> dict[str, Any]:
    """URLs that must **not** be reachable; ``reachable: true`` means the isolation check failed."""
    settings = get_settings()
    network_label = _sickz_network_label(settings)
    runtime = _sickz_runtime_block(settings)
    homelab_icon_by_tunnel: dict[str, str] | None = None
    homelab_name_by_tunnel: dict[str, str] | None = None
    homelab_groups: list[list[str]] = []
    if _sickz_targets_equal_default_catalog_mode(settings.sickz_targets):
        homelab_groups, homelab_icon_by_tunnel, homelab_name_by_tunnel = await homelab_sickz_catalog_for_sickz()

    if _known_paas_runtime_detected() and (settings.sickz_internal_network or _sickz_implicit_internal_network(settings)):
        _log.debug(
            "Home LAN skip would apply (env or implicit label/domain) but a cloud/PaaS runtime was detected; sickz probes still run.",
        )

    if _sickz_internal_network_effective(settings):
        groups = _ensure_pfsense_sickz_group(
            _parse_sickz_target_groups(settings.sickz_targets) + homelab_groups,
        )
        group_keys = [" | ".join(g) for g in groups]
        skip_reason = "Not probed (LAN / internal network skip)."
        checks = {
            key: {
                "skipped": True,
                "aliases_probed": list(g),
                "reason": skip_reason,
                "tls_trusted": None,
                **_sickz_row_ui_metadata(g, homelab_icon_by_tunnel, homelab_name_by_tunnel),
                **_sickz_pfsense_tcp_skip_payload(g),
            }
            for key, g in zip(group_keys, groups, strict=True)
        }
        return {
            "checks": checks,
            "version": request.app.version,
            "status": "skipped_internal_network",
            "network_label": network_label,
            "runtime": runtime,
            "detail": _sickz_skip_detail(settings),
        }

    groups = _ensure_pfsense_sickz_group(
        _parse_sickz_target_groups(settings.sickz_targets) + homelab_groups,
    )
    if not groups:
        return {
            "checks": {},
            "version": request.app.version,
            "status": "no_targets",
            "network_label": network_label,
            "runtime": runtime,
            "detail": "SICKZ_TARGETS is empty; add comma- or newline-separated URL groups to probe.",
        }
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    group_keys = [" | ".join(g) for g in groups]
    group_results = await asyncio.gather(
        *(_probe_sickz_alias_group(g, homelab_icon_by_tunnel, homelab_name_by_tunnel) for g in groups),
    )
    checks = dict(zip(group_keys, group_results, strict=True))
    return {
        "checks": checks,
        "version": request.app.version,
        "network_label": network_label,
        "runtime": runtime,
    }
