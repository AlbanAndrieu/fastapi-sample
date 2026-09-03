"""Contract tests for centralized external-provider cache policies."""

from dataclasses import asdict

from nabla.api.provider_probe_policies import (
    CLOUDFLARE_EXPOSURE_CACHE_POLICY,
    CLOUDFLARE_TUNNELS_CACHE_POLICY,
    PFSENSE_LIVENESS_CACHE_POLICY,
    PFSENSE_POSTURE_CACHE_POLICY,
    PFSENSE_SNORT2C_CACHE_POLICY,
    TRUENAS_API_CACHE_POLICY,
)


def test_truenas_cache_budget_is_failure_protective() -> None:
    assert asdict(TRUENAS_API_CACHE_POLICY) == {
        "success_ttl": 60.0,
        "failure_ttl": 120.0,
        "stale_ttl": 600.0,
        "lock_ttl": 20,
        "wait_timeout": 0.6,
        "poll_interval": 0.1,
    }


def test_pfsense_cache_budgets_are_reviewable_together() -> None:
    for policy in (
        PFSENSE_LIVENESS_CACHE_POLICY,
        PFSENSE_POSTURE_CACHE_POLICY,
        PFSENSE_SNORT2C_CACHE_POLICY,
    ):
        assert policy.success_ttl == 60.0
        assert policy.failure_ttl == 120.0
        assert policy.stale_ttl == 600.0

    assert PFSENSE_LIVENESS_CACHE_POLICY.lock_ttl == 15
    assert PFSENSE_POSTURE_CACHE_POLICY.lock_ttl == 15
    assert PFSENSE_SNORT2C_CACHE_POLICY.lock_ttl == 15


def test_cloudflare_cache_budgets_keep_probe_specific_lock_ttls() -> None:
    for policy in (
        CLOUDFLARE_TUNNELS_CACHE_POLICY,
        CLOUDFLARE_EXPOSURE_CACHE_POLICY,
    ):
        assert policy.success_ttl == 90.0
        assert policy.failure_ttl == 60.0
        assert policy.stale_ttl == 600.0

    assert CLOUDFLARE_TUNNELS_CACHE_POLICY.lock_ttl == 15
    assert CLOUDFLARE_EXPOSURE_CACHE_POLICY.lock_ttl == 20
