"""Contract tests for code-owned declared service metadata."""

from pydantic import ValidationError
import pytest

from nabla.api.homelab_declared import DeclaredServiceCatalog


def _catalog(service: dict[str, object]) -> DeclaredServiceCatalog:
    return DeclaredServiceCatalog.model_validate(
        {
            "version": 1,
            "catalogRevision": "sha256:test",
            "topologyVersion": 1,
            "name": "test",
            "services": [service],
        }
    )


def test_declared_service_preserves_presentation_and_security_metadata() -> None:
    catalog = _catalog(
        {
            "id": "wazuh",
            "name": "Wazuh",
            "kind": "siem",
            "category": "security",
            "presentationRole": "service",
            "criticality": "high",
            "securityFunctions": ["identify", "protect", "detect", "respond"],
            "sourcePath": "apps/wazuh/compose.yml",
            "composeService": "wazuh",
            "runtime": {
                "provider": "truenas-app",
                "containerService": "wazuh",
            },
        }
    )

    service = catalog.services[0]
    assert service.presentation_role == "service"
    assert service.criticality == "high"
    assert service.security_functions == [
        "identify",
        "protect",
        "detect",
        "respond",
    ]

    payload = catalog.model_dump(mode="json", by_alias=True, exclude_none=True)
    serialized = payload["services"][0]
    assert serialized["presentationRole"] == "service"
    assert serialized["criticality"] == "high"
    assert serialized["securityFunctions"] == [
        "identify",
        "protect",
        "detect",
        "respond",
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("presentationRole", "database"),
        ("criticality", "urgent"),
        ("securityFunctions", ["prevent"]),
    ],
)
def test_declared_service_rejects_unknown_metadata_values(
    field: str,
    value: object,
) -> None:
    service: dict[str, object] = {
        "id": "wazuh",
        "name": "Wazuh",
        "kind": "siem",
        "category": "security",
        "sourcePath": "apps/wazuh/compose.yml",
        "composeService": "wazuh",
        field: value,
    }

    with pytest.raises(ValidationError):
        _catalog(service)


def test_declared_service_rejects_duplicate_security_functions() -> None:
    with pytest.raises(ValidationError, match="securityFunctions must not contain duplicates"):
        _catalog(
            {
                "id": "wazuh",
                "name": "Wazuh",
                "kind": "siem",
                "category": "security",
                "securityFunctions": ["detect", "detect"],
                "sourcePath": "apps/wazuh/compose.yml",
                "composeService": "wazuh",
            }
        )
