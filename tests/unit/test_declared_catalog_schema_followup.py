"""Regression coverage for the current nabla-compose declared-service schema."""

from pydantic import ValidationError

from nabla.api.homelab_declared import (
    DeclaredServiceCatalog,
    _validation_error_summary,
)


def test_declared_catalog_accepts_runtime_networks_lifecycle_and_monitoring() -> None:
    catalog = DeclaredServiceCatalog.model_validate(
        {
            "version": 1,
            "catalogRevision": "sha256:" + "a" * 64,
            "topologyVersion": 1,
            "name": "Nabla homelab declared services",
            "services": [
                {
                    "id": "example-service",
                    "name": "Example service",
                    "kind": "application",
                    "category": "operations",
                    "sourcePath": "apps/example/compose.yml",
                    "composeService": "example",
                    "runtime": {
                        "provider": "truenas-app",
                        "containerService": "example",
                        "networks": ["intranet", "traefik_network"],
                    },
                    "lifecycle": {
                        "phase": "platform-services",
                        "priority": 40,
                    },
                    "monitoring": {
                        "type": "http",
                        "target": "http://172.17.0.24:8080/health",
                        "conditions": ["[STATUS] == 200"],
                    },
                }
            ],
        }
    )

    service = catalog.services[0]
    assert service.runtime is not None
    assert service.runtime.networks == ["intranet", "traefik_network"]
    assert service.lifecycle is not None
    assert service.lifecycle.phase == "platform-services"
    assert service.monitoring is not None
    assert service.monitoring.type == "http"


def test_declared_catalog_validation_log_summary_is_bounded() -> None:
    try:
        DeclaredServiceCatalog.model_validate(
            {
                "version": 1,
                "catalogRevision": "sha256:" + "b" * 64,
                "topologyVersion": 1,
                "name": "Nabla homelab declared services",
                "services": [
                    {
                        "id": "broken-service",
                        "name": "Broken service",
                        "kind": "application",
                        "category": "operations",
                        "sourcePath": "apps/broken/compose.yml",
                        "composeService": "broken",
                        "runtime": {
                            "provider": "truenas-app",
                            "containerService": "broken",
                            "networks": ["intranet", "intranet"],
                        },
                        "lifecycle": {"phase": "invalid", "priority": 5000},
                        "monitoring": {"type": "port", "port": 70000},
                    }
                ],
            }
        )
    except ValidationError as exc:
        summary = _validation_error_summary(exc)
    else:  # pragma: no cover - the invalid fixture must remain invalid
        raise AssertionError("invalid declared-service fixture unexpectedly validated")

    assert summary.startswith("errors=")
    assert "services.0" in summary
    assert "https://errors.pydantic.dev" not in summary
    assert "input_value=" not in summary
    assert len(summary) < 700
