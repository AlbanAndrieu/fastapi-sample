"""F14 (16/11): health states that disagreed with the runtime."""

from __future__ import annotations

from nabla.api.homelab_declared import RuntimeBinding
from nabla.api.homelab_runtime import ObservedApp, TrueNASRuntimeSnapshot
from nabla.api.homelab_runtime_models import ObservedContainer
from nabla.api.homelab_service_health import build_reconciled_service_health, mark_not_deployed
from tests.unit.catalog_v2_fixture import service as v2_service


def _runtime(*apps: ObservedApp, stale: bool = False) -> TrueNASRuntimeSnapshot:
    return TrueNASRuntimeSnapshot(
        observed_at="2026-09-10T18:00:00Z",
        configured=True,
        reachable=True,
        stale=stale,
        apps=list(apps),
    )


def test_refused_probe_on_a_probe_path_route_is_fail_not_unknown() -> None:
    # F14 (16/11): the probe URL ends with probePath, the route URL does not; join on the id.
    service = v2_service("prometheus", "https://prometheus.albandrieu.com", title="Prometheus", public=True)
    rows = build_reconciled_service_health(
        [service],
        public_results=[
            {
                "id": "prometheus",
                "url": "https://prometheus.albandrieu.com/-/healthy",
                "reachable": False,
                "http_status": 0,
                "state": "fail",
                "error_kind": "connection_refused",
                "probe_stale": False,
            },
        ],
        internal_results=[],
        runtime=None,
        tunnels=[],
    )

    assert rows[0]["direct_state"] == "fail"
    assert rows[0]["state"] == "fail"


def test_binding_matched_by_two_apps_is_unknown_not_missing() -> None:
    # F14 (16/11): Redis (containerService only) matched several apps and was reported missing,
    # which degraded its eight required dependents.
    service = v2_service("redis", title="Redis", public=False)
    binding = RuntimeBinding(provider="truenas-app", containerService="redis")
    apps = [ObservedApp(app_id=name, name=name, state="RUNNING", containers=[ObservedContainer(service_name="redis", state="running")]) for name in ("redis", "paperless")]
    row = build_reconciled_service_health(
        [service],
        public_results=[],
        internal_results=[],
        runtime=_runtime(*apps),
        tunnels=[],
        runtime_bindings={"redis": binding},
    )[0]
    assert row["runtime_missing"] is False
    assert row["state"] == "unknown"


def test_origin_5xx_behind_access_is_fail_even_with_open_lan_port() -> None:
    # F14 (16/11): Uptime Kuma answered 5xx after the service token passed Access and showed warn.
    service = v2_service("uptime-kuma", "https://uptime-kuma.albandrieu.com", title="Uptime Kuma", public=True)
    rows = build_reconciled_service_health(
        [service],
        public_results=[
            {
                "id": "uptime-kuma",
                "url": "https://uptime-kuma.albandrieu.com/",
                "reachable": True,
                "http_status": 502,
                "state": "fail",
                "origin_reached": True,
                "probe_stale": False,
            },
        ],
        internal_results=[{"id": "uptime-kuma", "state": "ok", "reachable": True, "probe_stale": False}],
        runtime=None,
        tunnels=[],
    )
    assert rows[0]["state"] == "fail"


def test_planned_app_without_runtime_is_not_deployed_not_an_outage() -> None:
    planned = v2_service("netbox", title="NetBox", public=False).model_copy(update={"lifecycle": "planned"})
    active = v2_service("gatus", title="Gatus", public=False).model_copy(update={"lifecycle": "active"})
    rows = [
        {"id": "netbox", "state": "fail", "local_state": "fail", "effective_state": "fail"},
        {"id": "gatus", "state": "fail", "local_state": "fail", "effective_state": "fail"},
    ]
    marked = {row["id"]: row for row in mark_not_deployed(rows, [planned, active])}
    assert marked["netbox"] == {
        "id": "netbox",
        "state": "unknown",
        "local_state": "unknown",
        "effective_state": "unknown",
        "lifecycle": "planned",
        "not_deployed": True,
    }
    assert marked["gatus"]["state"] == "fail"
