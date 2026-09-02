"""Contract tests for declared/observed homelab reconciliation."""

from __future__ import annotations

import pytest

import nabla.api.homelab_runtime as homelab_runtime
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
                    },
                ],
            },
        },
    )

    assert app.app_id == "litellm-albandrieu"
    assert app.containers[0].service_name == "litellm"


def test_runtime_retries_one_transient_connection_reset(monkeypatch) -> None:
    class ResetOnceAdapter:
        calls = 0

        def list_apps(self):
            self.calls += 1
            if self.calls == 1:
                raise ConnectionResetError(104, "Connection reset by peer")
            return [{"id": "n8n", "state": "RUNNING"}]

    adapter = ResetOnceAdapter()
    monkeypatch.setattr(homelab_runtime, "build_truenas_adapter", lambda: adapter)
    monkeypatch.setattr(homelab_runtime.time, "sleep", lambda _seconds: None)

    snapshot = homelab_runtime.observe_truenas_runtime()

    assert adapter.calls == 2
    assert snapshot.reachable is True
    assert snapshot.apps[0].app_id == "n8n"


def test_runtime_does_not_hide_persistent_connection_reset(monkeypatch) -> None:
    class ResetAdapter:
        calls = 0

        def list_apps(self):
            self.calls += 1
            raise ConnectionResetError(104, "Connection reset by peer")

    adapter = ResetAdapter()
    monkeypatch.setattr(homelab_runtime, "build_truenas_adapter", lambda: adapter)
    monkeypatch.setattr(homelab_runtime.time, "sleep", lambda _seconds: None)

    snapshot = homelab_runtime.observe_truenas_runtime()

    assert adapter.calls == 3
    assert snapshot.reachable is False
    assert "Connection reset by peer" in str(snapshot.error)


def test_runtime_cache_reuses_one_observation(monkeypatch) -> None:
    homelab_runtime._reset_runtime_cache()
    calls = 0
    snapshot = TrueNASRuntimeSnapshot(
        observed_at="2026-08-25T20:00:00Z",
        configured=True,
        reachable=True,
    )

    def fake_observe() -> TrueNASRuntimeSnapshot:
        nonlocal calls
        calls += 1
        return snapshot

    monkeypatch.setattr(homelab_runtime, "observe_truenas_runtime", fake_observe)
    try:
        first = homelab_runtime._cached_truenas_runtime()
        second = homelab_runtime._cached_truenas_runtime()
    finally:
        homelab_runtime._reset_runtime_cache()

    assert first is second
    assert calls == 1


def test_runtime_cache_serves_last_known_good_after_refresh_failure(monkeypatch) -> None:
    homelab_runtime._reset_runtime_cache()
    good = TrueNASRuntimeSnapshot(
        observed_at="2026-08-25T20:00:00Z",
        configured=True,
        reachable=True,
        apps=[_observed_app({"id": "openwebui", "state": "RUNNING"})],
    )
    failed = TrueNASRuntimeSnapshot(
        observed_at="2026-08-25T20:01:00Z",
        configured=True,
        reachable=False,
        error="temporary websocket failure",
    )
    snapshots = iter([good, failed])
    monkeypatch.setattr(
        homelab_runtime,
        "observe_truenas_runtime",
        lambda: next(snapshots),
    )

    try:
        first = homelab_runtime._cached_truenas_runtime()
        monkeypatch.setattr(homelab_runtime, "_RUNTIME_CACHE_EXPIRES_AT", 0.0)
        second = homelab_runtime._cached_truenas_runtime()
    finally:
        homelab_runtime._reset_runtime_cache()

    assert first.reachable is True
    assert second.reachable is True
    assert second.stale is True
    assert second.apps[0].app_id == "openwebui"
    assert second.error == "temporary websocket failure"


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
                },
            ],
        },
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
                    "active_workloads": {"container_details": [{"service_name": "litellm", "state": "running"}]},
                },
            ),
        ],
    )

    async def fake_catalog():
        return catalog

    async def fake_runtime():
        return runtime

    monkeypatch.setattr("nabla.api.homelab_runtime.fetch_declared_service_catalog", fake_catalog)
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
        },
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

    monkeypatch.setattr("nabla.api.homelab_runtime.fetch_declared_service_catalog", fake_catalog)
    monkeypatch.setattr("nabla.api.homelab_runtime.fetch_truenas_runtime", fake_runtime)

    payload = await build_homelab_status_payload()

    assert payload["observedOnly"][0]["reconciliation"] == "observed_only"
    assert payload["observedOnly"][0]["observed"]["appId"] == "legacy-app"
