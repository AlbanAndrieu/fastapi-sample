"""Resolve canonical monitoring targets exported by nabla-compose."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from nabla.api.homelab_declared import DeclaredService
from nabla.api.homelab_models import HomelabService


def public_monitoring_url(
    service: HomelabService,
    declared: DeclaredService | None,
) -> str | None:
    """Apply a canonical HTTP health path/query to the declared public endpoint.

    ``x-nabla.monitoring`` normally points at the trusted LAN origin. Public
    reachability must keep the tunnel host/scheme while reusing only the
    functional path and query. This prevents root-page behavior from being
    mistaken for application health without creating per-service overrides.
    """
    public_url = service.public_https_probe_url
    if public_url is None or declared is None or declared.monitoring is None:
        return public_url
    monitoring = declared.monitoring
    if monitoring.probe_type != "http":
        return public_url
    raw_target = monitoring.target or monitoring.url
    if not raw_target:
        return public_url

    target = urlsplit(raw_target)
    if target.scheme not in {"http", "https"} or not target.netloc:
        return public_url
    public = urlsplit(public_url)
    return urlunsplit(
        (
            public.scheme,
            public.netloc,
            target.path or "/",
            target.query,
            "",
        ),
    )
