"""Bounded sampling policy for interactive homelab service probes."""

from __future__ import annotations

import math
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
        "garage",
        "garage-webui",
        "vaultwarden",
    },
)


def _unique_services(services: list[HomelabService]) -> list[HomelabService]:
    """Keep the first declaration for each service id to avoid duplicate probes."""
    unique: list[HomelabService] = []
    seen: set[str] = set()
    for service in services:
        service_id = service.service_id
        if service_id in seen:
            continue
        seen.add(service_id)
        unique.append(service)
    return unique


def _probe_partitions(
    services: list[HomelabService],
    limit: int,
) -> tuple[list[HomelabService], list[HomelabService]]:
    """Reserve rotating slots even when priority count reaches the probe budget."""
    if limit <= 0:
        return [], []
    # Put Garage first so its three distinct internal targets remain observable.
    garage_ids = {"garage", "garage-admin", "garage-webui"}
    priority = [item for item in services if item.service_id in garage_ids]
    priority.extend(item for item in services if item.service_id in _PRIORITY_SERVICE_IDS and item.service_id not in garage_ids)
    reserved = 2 if limit > 3 and len(services) > limit else 0
    fixed = priority[: limit - reserved]
    fixed_ids = {item.service_id for item in fixed}
    rotating = [item for item in services if item.service_id not in fixed_ids]
    return fixed, rotating


def select_probe_subset(
    services: list[HomelabService],
    *,
    limit: int,
    now: float | None = None,
) -> list[HomelabService]:
    """Always preserve rotating capacity and bounded Garage coverage."""
    services = _unique_services(services)
    if limit <= 0:
        return []
    if len(services) <= limit:
        return list(services)

    fixed, remainder = _probe_partitions(services, limit)
    slots = limit - len(fixed)
    clock = time.monotonic() if now is None else now
    bucket = int(clock // HEALTH_CACHE_TTL_SEC)
    start = (bucket * slots) % len(remainder)
    rotating = [remainder[(start + offset) % len(remainder)] for offset in range(min(slots, len(remainder)))]
    return [*fixed, *rotating]


def estimated_probe_interval_seconds(
    service: HomelabService,
    *,
    eligible_services: list[HomelabService],
    limit: int,
) -> float | None:
    """Estimate probe interval under the same fixed/rotating budget policy."""
    eligible_services = _unique_services(eligible_services)
    if limit <= 0 or service not in eligible_services:
        return None
    if len(eligible_services) <= limit:
        return HEALTH_CACHE_TTL_SEC
    fixed, remainder = _probe_partitions(eligible_services, limit)
    if service in fixed:
        return HEALTH_CACHE_TTL_SEC
    slots = limit - len(fixed)
    rounds = max(1, math.ceil(len(remainder) / slots))
    return HEALTH_CACHE_TTL_SEC * rounds
