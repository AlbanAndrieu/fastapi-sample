from __future__ import annotations

from nabla.api.services import merge_services
from nabla.integrations.truenas_apps import app_to_service


def test_app_to_service_exposes_containers_and_port_mappings(monkeypatch) -> None:
    monkeypatch.setattr("nabla.integrations.truenas_apps.TRUENAS_URL", "https://nas.test:7000")
    app = {
        "id": "demo",
        "name": "demo",
        "state": "RUNNING",
        "version": "1.2.3",
        "active_workloads": {
            "containers": 1,
            "images": ["example/demo:1.2.3"],
            "used_ports": [
                {
                    "container_port": 8080,
                    "host_ports": [
                        {"host_ip": "127.0.0.1", "host_port": 31028},
                        {"host_ip": "::", "host_port": 31028},
                    ],
                    "protocol": "tcp",
                },
            ],
            "container_details": [
                {
                    "id": "abc",
                    "service_name": "web",
                    "image": "example/demo:1.2.3",
                    "state": "running",
                    "port_config": [
                        {
                            "container_port": 8080,
                            "host_ports": [{"host_ip": "127.0.0.1", "host_port": 31028}],
                            "protocol": "tcp",
                        },
                    ],
                },
            ],
        },
    }

    service = app_to_service(app)

    assert service["internalPort"] == 31028
    assert service["hostPorts"] == [31028]
    assert service["ports"][0]["containerPort"] == 8080
    assert service["containers"][0]["image"] == "example/demo:1.2.3"


def test_merge_prefers_curated_port_when_truenas_confirms_it() -> None:
    reference = [{"name": "Open WebUI", "internalPort": 9099, "description": "UI"}]
    live = [
        {
            "name": "openwebui",
            "internalPort": 31028,
            "hostPorts": [31028, 9099],
            "containers": [],
        },
    ]

    merged = merge_services(reference, live)

    assert len(merged) == 1
    assert merged[0]["internalPort"] == 9099
    assert merged[0]["description"] == "UI"
