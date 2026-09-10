"""Regression tests for Cloudflare exposure uncertainty and empty inventories."""

import asyncio

from nabla.api import homelab_exposure
from nabla.api.homelab_exposure import CloudflareExposureSnapshot


def test_configured_empty_cloudflare_snapshot_is_unconfirmed_warning() -> None:
    summary = CloudflareExposureSnapshot(configured=True).summary()

    assert summary["status_confirmed"] is False
    assert summary["inventory_confirmed"] is False
    assert summary["tunnel_observer_state"] == "empty"
    assert summary["warning"].startswith("⚠️")


def test_empty_cloudflare_tunnel_inventory_is_not_cache_success() -> None:
    payload = {
        "configured": True,
        "tunnels": [],
        "access_applications": [],
        "tunnel_error": None,
        "access_error": None,
    }

    assert homelab_exposure._cloudflare_exposure_success(payload) is False
    assert homelab_exposure._refresh_error(payload) == "empty_tunnel_inventory"


def test_empty_provider_tunnel_result_is_classified_as_observation_failure(
    monkeypatch,
) -> None:
    monkeypatch.setattr(homelab_exposure, "observe_cloudflare_tunnels", lambda: [])
    monkeypatch.setattr(
        homelab_exposure,
        "observe_cloudflare_access_applications",
        lambda: [],
    )

    payload = asyncio.run(homelab_exposure._observe_cloudflare_exposure_origin())

    assert payload["tunnels"] == []
    assert payload["tunnel_error"] == "empty_tunnel_inventory"
    assert homelab_exposure._cloudflare_exposure_success(payload) is False


def test_stale_cloudflare_snapshot_is_diagnostic_only_for_edge_reconciliation() -> None:
    snapshot = CloudflareExposureSnapshot(
        configured=True,
        stale=True,
        refresh_error="TimeoutError",
    )

    mismatches, incomplete = homelab_exposure._edge_reconciliation_reasons(
        "cloudflare",
        None,
        snapshot,
    )

    assert mismatches == []
    assert incomplete == ["Cloudflare global status could not be confirmed"]
