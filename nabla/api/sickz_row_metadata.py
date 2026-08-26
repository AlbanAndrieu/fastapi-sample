"""Display metadata helpers for ``/sickz`` probe rows."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from nabla.api.sickz_pfsense import pfsense_canonical_href
from nabla.config_settings import _ALBANDRIEU_PUBLIC_DOMAIN_SUFFIX

_ALBANDRIEU_COM = f".{_ALBANDRIEU_PUBLIC_DOMAIN_SUFFIX}"
_ICON_FILENAME_RE = re.compile(
    r"^[a-z0-9][a-z0-9._-]*\.svg\Z",
    re.IGNORECASE,
)


def _validate_icon_filename(name: str) -> str:
    value = name.strip()
    if _ICON_FILENAME_RE.match(value):
        return value
    return "homepage.svg"


def _ipv4_host(host: str) -> bool:
    parts = host.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False


def _short_label_for_url(url: str) -> str:
    raw = url.strip()
    parsed = urlparse(raw)
    host = (parsed.hostname or "").strip().lower()
    port = parsed.port
    if not host:
        tail = re.sub(r"^https?://", "", raw, flags=re.I)
        return (tail[:48] + "…") if len(tail) > 48 else tail
    display = host.removesuffix(_ALBANDRIEU_COM)
    if port and port not in (80, 443):
        return f"{display}:{port}"
    return display


def _display_label(urls: list[str]) -> str:
    if not urls:
        return "target"
    return " · ".join(_short_label_for_url(url) for url in urls)


def _row_href(urls: list[str]) -> str:
    return urls[0].strip() if urls else ""


def _canonical_https_tunnel_key(url: str) -> str:
    value = url.strip()
    if not value.lower().startswith("https://"):
        return value
    return value.rstrip("/") + "/"


def _homelab_icon_src_for_urls(
    urls: list[str],
    homelab_icon_by_tunnel: dict[str, str] | None,
) -> str | None:
    if not homelab_icon_by_tunnel:
        return None
    for raw in urls:
        hit = homelab_icon_by_tunnel.get(_canonical_https_tunnel_key(raw))
        if hit:
            return hit
    return None


def _homelab_service_name_for_urls(
    urls: list[str],
    homelab_name_by_tunnel: dict[str, str] | None,
) -> str | None:
    if not homelab_name_by_tunnel:
        return None
    for raw in urls:
        hit = homelab_name_by_tunnel.get(_canonical_https_tunnel_key(raw))
        if hit:
            return hit
    return None


def _icon_filename(urls: list[str]) -> str:
    if not urls:
        return _validate_icon_filename("homepage.svg")
    parsed = urlparse(urls[0].strip())
    if parsed.port == 10443:
        return _validate_icon_filename("pfsense.svg")
    host = (parsed.hostname or "").strip().lower()
    if _ipv4_host(host):
        return _validate_icon_filename("pfsense.svg")
    return _validate_icon_filename("homepage.svg")


def row_href(urls: list[str]) -> str:
    """Return the primary URL for a logical probe group."""
    return _row_href(urls)


def row_ui_metadata(
    urls: list[str],
    homelab_icon_by_tunnel: dict[str, str] | None = None,
    homelab_name_by_tunnel: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build stable UI metadata without mixing it with network probing."""
    pf_href = pfsense_canonical_href(urls)
    if pf_href is not None:
        return {
            "display_label": "PfSense",
            "name": "PfSense",
            "href": pf_href,
            "tunnel_url": pf_href,
            "icon_filename": _validate_icon_filename("pfsense.svg"),
        }
    href = _row_href(urls).strip()
    catalog_name = _homelab_service_name_for_urls(
        urls,
        homelab_name_by_tunnel,
    )
    display = catalog_name if catalog_name else _display_label(urls)
    icon_src = _homelab_icon_src_for_urls(urls, homelab_icon_by_tunnel)
    base: dict[str, Any] = {
        "display_label": display,
        "href": href,
        "tunnel_url": href,
        "icon_filename": _icon_filename(urls),
    }
    if catalog_name:
        base["name"] = catalog_name
    if icon_src:
        base["icon_src"] = icon_src
    return base
