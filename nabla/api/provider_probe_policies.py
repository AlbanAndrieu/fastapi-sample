"""Centralized cache policies for external provider health probes."""

from __future__ import annotations

from nabla.api.external_probe_cache_types import ProbeCachePolicy

TRUENAS_API_CACHE_POLICY = ProbeCachePolicy(
    success_ttl=60.0,
    failure_ttl=120.0,
    stale_ttl=600.0,
    lock_ttl=20,
)

PFSENSE_LIVENESS_CACHE_POLICY = ProbeCachePolicy(
    success_ttl=60.0,
    failure_ttl=120.0,
    stale_ttl=600.0,
)

PFSENSE_POSTURE_CACHE_POLICY = ProbeCachePolicy(
    success_ttl=60.0,
    failure_ttl=120.0,
    stale_ttl=600.0,
    lock_ttl=15,
)

PFSENSE_SNORT2C_CACHE_POLICY = ProbeCachePolicy(
    success_ttl=60.0,
    failure_ttl=120.0,
    stale_ttl=600.0,
    lock_ttl=15,
)

CLOUDFLARE_TUNNELS_CACHE_POLICY = ProbeCachePolicy(
    success_ttl=90.0,
    failure_ttl=60.0,
    stale_ttl=600.0,
)

CLOUDFLARE_EXPOSURE_CACHE_POLICY = ProbeCachePolicy(
    success_ttl=90.0,
    failure_ttl=60.0,
    stale_ttl=600.0,
    lock_ttl=20,
)
