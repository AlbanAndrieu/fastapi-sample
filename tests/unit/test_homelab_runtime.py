"""Contract tests for declared/observed homelab reconciliation."""

from __future__ import annotations

import pytest

from nabla.api.homelab_declared import DeclaredServiceCatalog
from nabla.api.homelab_runtime import (
    TrueNASRuntimeSnapshot,
    _observed_app,
    build_homelab_status_payload,
)


def test_observed_app_preserves_truenas_container_service_name() -> None:
    app = _observed_app(
        {
            "id": "litellm-albandrieu",
            "name": "litellm-albandrieu",
            "state": "RUNNING",
            "active_workloads": {
                "container_details": [
                    {
                        "service_name": "litellm",
                        "image": "ghcr.io/berriai/litellm:main-stable",
                        "state": "running",
                    }
                ]
            },
        }
    )

    assert app.app_id == "litellm-albandrieu"
    assert app.containers[0].service_name == "litellm"


@pytest.mark.asyncio
async def test_status_matches_declared_service_by_container_service(monkeypatch) -> None:
    catalog = DeclaredServiceCatalog.model_validate(
        {
            "version": 1,
            "catalogRevision": "sha256:test",
            "topologyVersion": 1,
            "name": "test",
            "services": [
                {
                    "id": "litellm",
                    "name": "LiteLLM",
                    "kind": "gateway",
                    "category": "ai",
                    "sourcePath": "apps/litellm/compose.yml",
                    "composeService": "litellm",
                    "runtime": {
                        "provider": "truenas-app",
                        "containerService": "litellm",
                    },
                }
            ],
        }
    )
    runtime = TrueNASRuntimeSnapshot(
        observed_at="2026-08-24T16:00:00Z",
        configured=True,
        reachable=True,
        apps=[
            _observed_app(
                {
                    "id": "litellm-albandrieu",
                    "name": "litellm-albandrieu",
                    "state": "RUNNING",
                    "active_workloads": {
                        "container_details": [
                            {"service_name": "litellm", "state": "running"}
                        ]
                    },
                }
            )
        ],
    )

    async def fake_catalog():
        return catalog

    async def fake_runtime():
        return runtime

    monkeypatch.setattr(
        "nabla.api.homelab_runtime.fetch_declared_service_catalog", fake_catalog
    )
    monkeypatch.setattr("nabla.api.homelab_runtime.fetch_truenas_runtime", fake_runtime)

    payload = await build_homelab_status_payload()

    assert payload["services"][0]["reconciliation"] == "in_sync"
    assert payload["services"][0]["observed"]["appId"] == "litellm-albandrieu"
    assert payload["observedOnly"] == []


@pytest.mark.asyncio
async def test_status_reports_unmanaged_truenas_apps(monkeypatch) -> None:
    catalog = DeclaredServiceCatalog.model_validate(
        {
            "version": 1,
            "catalogRevision": "sha256:test",
            "topologyVersion": 1,
            "name": "test",
            "services": [],
        }
    )
    runtime = TrueNASRuntimeSnapshot(
        observed_at="2026-08-24T16:00:00Z",
        configured=True,
        reachable=True,
        apps=[_observed_app({"id": "legacy-app", "state": "RUNNING"})],
    )

    async def fake_catalog():
        return catalog

    async def fake_runtime():
        return runtime

    monkeypatch.setattr(
        "nabla.api.homelab_runtime.fetch_declared_service_catalog", fake_catalog
    )
    monkeypatch.setattr("nabla.api.homelab_runtime.fetch_truenas_runtime", fake_runtime)

    payload = await build_homelab_status_payload()

    assert payload["observedOnly"][0]["reconciliation"] == "observed_only"
    assert payload["observedOnly"][0]["observed"]["appId"] == "legacy-app"
