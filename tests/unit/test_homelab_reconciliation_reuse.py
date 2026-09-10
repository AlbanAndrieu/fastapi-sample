"""Regression tests for homelab reconciliation reuse and freshness UI."""

from __future__ import annotations

from pathlib import Path

from nabla.api.homelab_declared import RuntimeBinding
from nabla.api.homelab_runtime import (
    match_runtime_binding,
    runtime_snapshot_from_health_api,
)

ROOT = Path(__file__).resolve().parents[2]


def test_runtime_snapshot_reuses_true_nas_health_app_inventory() -> None:
    snapshot = runtime_snapshot_from_health_api(
        {
            "reachable": True,
            "stale": False,
            "last_success_at": "2026-09-09T14:21:06Z",
            "apps": [
                {
                    "id": "n8n",
                    "name": "n8n",
                    "state": "RUNNING",
                    "upgrade_available": True,
                },
            ],
        },
    )

    assert snapshot is not None
    assert snapshot.reachable is True
    assert snapshot.stale is False
    assert snapshot.observed_at == "2026-09-09T14:21:06Z"
    assert [app.app_id for app in snapshot.apps] == ["n8n"]


def test_runtime_snapshot_reuses_container_service_identity() -> None:
    snapshot = runtime_snapshot_from_health_api(
        {
            "reachable": True,
            "stale": False,
            "last_success_at": "2026-09-09T16:00:00Z",
            "apps": [
                {
                    "id": "vaultwarden",
                    "name": "vaultwarden",
                    "state": "RUNNING",
                    "active_workloads": {
                        "container_details": [
                            {
                                "service_name": "vaultwarden",
                                "image": "vaultwarden/server:latest",
                                "state": "running",
                            },
                        ],
                    },
                },
            ],
        },
    )

    assert snapshot is not None
    matched, container = match_runtime_binding(
        snapshot.apps[0],
        RuntimeBinding(
            provider="truenas-app",
            containerService="vaultwarden",
        ),
    )
    assert matched is True
    assert container is not None
    assert container.service_name == "vaultwarden"


def test_runtime_snapshot_uses_stale_last_good_inventory() -> None:
    snapshot = runtime_snapshot_from_health_api(
        {
            "reachable": False,
            "stale": True,
            "error": "refresh failed",
            "last_good": {
                "last_success_at": "2026-09-09T14:20:00Z",
                "apps": [{"id": "redis", "name": "redis", "state": "RUNNING"}],
            },
        },
    )

    assert snapshot is not None
    assert snapshot.reachable is True
    assert snapshot.stale is True
    assert snapshot.error == "refresh failed"
    assert [app.app_id for app in snapshot.apps] == ["redis"]


def test_health_board_overlaps_reconciliation_with_probe_collection() -> None:
    source = (ROOT / "nabla/api/health_board.py").read_text(encoding="utf-8")

    assert "prepare_homelab_reconciliation_context(services)" in source
    assert "build_homelab_health_payload(catalog_services=services)" in source
    assert "context=reconciliation_context" in source


def test_health_ui_exposes_snapshot_and_probe_freshness() -> None:
    ui = (ROOT / "nabla/api/ui.py").read_text(encoding="utf-8")
    health = (ROOT / "nabla/api/assets/api-health-core.js").read_text(
        encoding="utf-8",
    )
    truenas = (ROOT / "nabla/api/assets/api-truenas.js").read_text(
        encoding="utf-8",
    )

    assert 'id="health-board-freshness"' in ui
    assert "renderSnapshotFreshness" in health
    assert "cached snapshot" in health
    assert "probe_cache" in truenas
    assert "probes from memory cache" in truenas
    assert "sampled" in truenas
    assert "eligible" in truenas
