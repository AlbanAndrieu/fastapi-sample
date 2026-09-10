from nabla.api.homelab_declared import RuntimeBinding
from nabla.api.homelab_health_evidence import build_reconciled_service_health
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_runtime import TrueNASRuntimeSnapshot, _observed_app


def test_truenas_container_state_and_health_are_preserved() -> None:
    app = _observed_app(
        {
            "id": "languagetool",
            "name": "languagetool",
            "state": "RUNNING",
            "active_workloads": {
                "container_details": [
                    {
                        "service_name": "languagetool",
                        "state": "running",
                        "health": {"status": "healthy"},
                    }
                ]
            },
        }
    )
    assert app.containers[0].state == "running"
    assert app.containers[0].health == "healthy"

    service = HomelabService(name="Language Tool", external=False)
    rows = build_reconciled_service_health(
        [service],
        public_results=[],
        internal_results=[],
        runtime=TrueNASRuntimeSnapshot(
            observed_at="2026-09-10T17:00:00Z",
            configured=True,
            reachable=True,
            apps=[app],
        ),
        tunnels=[],
        runtime_bindings={
            service.service_id: RuntimeBinding(
                provider="truenas-app",
                appId="languagetool",
                containerService="languagetool",
            )
        },
    )
    assert rows[0]["runtime_state"] == "RUNNING"
    assert rows[0]["runtime_containers"] == [
        {
            "service_name": "languagetool",
            "state": "running",
            "health": "healthy",
        }
    ]
