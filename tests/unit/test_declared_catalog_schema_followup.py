"""Regression coverage for the current nabla-compose declared-service schema."""

import pytest
from pydantic import ValidationError

from nabla.api.homelab_declared import (
    DeclaredServiceCatalog,
    _validation_error_summary,
)


def _catalog_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "$schema": "./services.schema.json",
        "version": 1,
        "catalogRevision": "sha256:" + "a" * 64,
        "topologyVersion": 1,
        "name": "Nabla homelab declared services",
        "services": [],
    }
    payload.update(updates)
    return payload


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
                    "status": "planned",
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
                        "blocksLaterWaves": False,
                    },
                    "internalUrl": "http://example:8080",
                    "monitoring": {
                        "type": "http",
                        "target": "http://172.17.0.24:8080/health",
                        "conditions": ["[STATUS] == 200"],
                    },
                },
            ],
        },
    )

    service = catalog.services[0]
    assert service.runtime is not None
    assert service.runtime.networks == ["intranet", "traefik_network"]
    assert service.lifecycle is not None
    assert service.status == "planned"
    assert service.internal_url == "http://example:8080"
    assert service.lifecycle.phase == "platform-services"
    assert service.lifecycle.blocks_later_waves is False
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
                    },
                ],
            },
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


def test_declared_catalog_v1_schema_metadata_is_validation_only() -> None:
    catalog = DeclaredServiceCatalog.model_validate(_catalog_payload())

    assert catalog.schema_uri == "./services.schema.json"
    assert "$schema" not in catalog.model_dump(mode="json", by_alias=True)


def test_declared_catalog_v1_contract_rejects_future_version() -> None:
    with pytest.raises(ValidationError):
        DeclaredServiceCatalog.model_validate(_catalog_payload(version=2))


def test_declared_catalog_v1_contract_rejects_unknown_top_level_fields() -> None:
    with pytest.raises(ValidationError):
        DeclaredServiceCatalog.model_validate(_catalog_payload(newV2Field=True))


@pytest.mark.parametrize(
    "revision",
    [
        "sha256:test",
        "main",
        "sha256:" + "g" * 64,
    ],
)
def test_declared_catalog_revision_must_be_canonical_sha256(revision: str) -> None:
    with pytest.raises(ValidationError):
        DeclaredServiceCatalog.model_validate(
            _catalog_payload(catalogRevision=revision),
        )

    fallback = DeclaredServiceCatalog.model_validate(
        _catalog_payload(catalogRevision="unavailable"),
    )
    assert fallback.catalog_revision == "unavailable"
