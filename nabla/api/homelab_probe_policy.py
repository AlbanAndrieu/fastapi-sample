"""Bounded sampling policy for interactive homelab service probes."""

from __future__ import annotations

import time

from nabla.api.homelab_models import HomelabService

HEALTH_CACHE_TTL_SEC = 30.0
MAX_PROBE_CONCURRENCY = 4
PUBLIC_PROBE_TIMEOUT_SEC = 3.0
INTERNAL_PROBE_TIMEOUT_SEC = 1.0
SERVICE_FANOUT_BUDGET_SEC = 4.0
MAX_INTERNAL_PROBES_PER_REFRESH = 12
MAX_PUBLIC_PROBES_PER_REFRESH = 12

_PRIORITY_SERVICE_IDS = frozenset(
    {
        "postgresql",
        "redis",
        "n8n",
        "prometheus",
        "grafana",
        "sentry",
        "pyroscope",
        "cloudflared",
        "garage-admin",
        "vaultwarden",
    },
)


def select_probe_subset(
    services: list[HomelabService],
    *,
    limit: int,
    now: float | None = None,
) -> list[HomelabService]:
    """Keep priority services in every refresh and rotate remaining targets."""
    if len(services) <= limit:
        return list(services)

    priority = [
        service
        for service in services
        if service.service_id in _PRIORITY_SERVICE_IDS
    ]
    if len(priority) >= limit:
        return priority[:limit]

    remainder = [
        service
        for service in services
        if service.service_id not in _PRIORITY_SERVICE_IDS
    ]
    slots = limit - len(priority)
    if not remainder or slots <= 0:
        return priority

    clock = time.monotonic() if now is None else now
    bucket = int(clock // HEALTH_CACHE_TTL_SEC)
    start = (bucket * slots) % len(remainder)
    rotating = [
        remainder[(start + offset) % len(remainder)]
        for offset in range(min(slots, len(remainder)))
    ]
    return [*priority, *rotating]
