"""Freshness regression tests for reconciled homelab health evidence."""

from nabla.api.homelab_health_evidence import build_reconciled_service_health
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_runtime import ObservedApp, TrueNASRuntimeSnapshot


def test_runtime_only_stale_observation_is_exposed_on_service_row() -> None:
    service = HomelabService(service_id="database", name="Database")
    runtime = TrueNASRuntimeSnapshot(
        observed_at="2000-01-01T00:00:00Z",
        configured=True,
        reachable=True,
        stale=True,
        apps=[
            ObservedApp(
                app_id="database",
                name="Database",
                state="ACTIVE",
            )
        ],
        error="TrueNAS refresh failed; serving last known good snapshot",
    )

    rows = build_reconciled_service_health(
        [service],
        public_results=[],
        internal_results=[],
        runtime=runtime,
        tunnels=[],
        checked_at="2099-01-01T00:00:00Z",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["state"] == "warn"
    assert row["runtime_state"] == "ACTIVE"
    assert row["observed_at"] == runtime.observed_at
    assert row["observation_stale"] is True
    assert row["observation_age_seconds"] > 0


def test_current_direct_probe_takes_freshness_precedence_over_stale_runtime() -> None:
    service = HomelabService(
        service_id="service",
        name="Service",
        tunnelUrl="https://service.albandrieu.com",
        external=True,
    )
    runtime = TrueNASRuntimeSnapshot(
        observed_at="2000-01-01T00:00:00Z",
        configured=True,
        reachable=True,
        stale=True,
        apps=[ObservedApp(app_id="service", name="Service", state="ACTIVE")],
    )
    checked_at = "2099-01-01T00:00:00Z"

    rows = build_reconciled_service_health(
        [service],
        public_results=[
            {
                "id": "service",
                "name": "Service",
                "url": "https://service.albandrieu.com/",
                "reachable": True,
                "http_status": 200,
                "state": "ok",
                "tls_trusted": True,
            }
        ],
        internal_results=[],
        runtime=runtime,
        tunnels=[],
        checked_at=checked_at,
    )

    row = rows[0]
    assert row["state"] == "ok"
    assert row["observed_at"] == checked_at
    assert row["observation_stale"] is False
    assert row["observation_age_seconds"] == 0


def test_stopped_truenas_app_without_workloads_remains_failed() -> None:
    service = HomelabService(service_id="n8n", name="n8n")
    runtime = TrueNASRuntimeSnapshot(
        observed_at="2099-01-01T00:00:00Z",
        configured=True,
        reachable=True,
        apps=[ObservedApp(app_id="n8n", name="n8n", state="STOPPED", containers=[])],
    )

    rows = build_reconciled_service_health(
        [service],
        public_results=[],
        internal_results=[],
        runtime=runtime,
        tunnels=[],
        checked_at="2099-01-01T00:00:00Z",
    )

    assert rows[0]["runtime_state"] == "STOPPED"
    assert rows[0]["state"] == "fail"
    assert rows[0]["observation_stale"] is False
