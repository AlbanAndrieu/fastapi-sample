"""Contract tests for catalog cutover identity, conditions and BIA projections."""

import pytest
from pydantic import ValidationError

from nabla.api.catalog_resource_model import (
    BackstageEntityRef,
    BusinessCriticalityProjection,
    DependencyCriticalityProjection,
    ReconciliationState,
    reconciliation_condition,
)


@pytest.mark.parametrize(
    "value",
    [
        "component:default/cartography",
        "resource:default/neo4j-security",
        "api:default/fastapi-sample",
        "system:default/nabla-homelab",
        "component:default/cartography_ui",
        "component:default/scorecard.v2",
        "template:default/service-template",
    ],
)
def test_backstage_entity_ref_accepts_canonical_full_refs(value: str) -> None:
    entity_ref = BackstageEntityRef.model_validate(value)

    assert entity_ref.model_dump() == value
    assert entity_ref.kind == value.split(":", 1)[0]
    assert entity_ref.namespace == "default"
    assert entity_ref.name == value.rsplit("/", 1)[1]


@pytest.mark.parametrize(
    "value",
    [
        "cartography",
        "component/cartography",
        "component:cartography",
        "Component:default/cartography",
        "component:default/Cartography",
        "component:default_/cartography",
        "component:default.namespace/cartography",
        "component:default/cartography__ui",
        "component:default/cartography..ui",
    ],
)
def test_backstage_entity_ref_rejects_ambiguous_or_noncanonical_refs(
    value: str,
) -> None:
    with pytest.raises(ValidationError):
        BackstageEntityRef.model_validate(value)



def test_backstage_entity_ref_rejects_oversized_namespace_or_name() -> None:
    with pytest.raises(ValidationError):
        BackstageEntityRef.model_validate(f"component:{'n' * 64}/service")
    with pytest.raises(ValidationError):
        BackstageEntityRef.model_validate(f"component:default/{'n' * 64}")


@pytest.mark.parametrize(
    ("state", "status", "reason"),
    [
        ("in_sync", "True", "InSync"),
        ("declared_only", "False", "DeclaredOnly"),
        ("observed_only", "False", "ObservedOnly"),
        ("binding_conflict", "False", "BindingConflict"),
        ("runtime_unknown", "Unknown", "RuntimeUnavailable"),
        ("not_observed", "Unknown", "ObservationNotApplicable"),
    ],
)
def test_reconciliation_condition_is_kubernetes_style(
    state: ReconciliationState,
    status: str,
    reason: str,
) -> None:
    condition = reconciliation_condition(state)
    payload = condition.model_dump(mode="json", by_alias=True, exclude_none=True)

    assert payload["type"] == "Reconciled"
    assert payload["status"] == status
    assert payload["reason"] == reason
    assert "lastTransitionTime" not in payload


def test_business_criticality_projection_matches_nabla_compose_contract() -> None:
    projection = BusinessCriticalityProjection.model_validate(
        {
            "entityRef": "component:default/fastapi-sample",
            "calculated": "high",
            "declared": "high",
            "status": "provisional",
            "mtpd": "P1D",
            "rto": "PT4H",
            "rpo": "PT1H",
            "mbco": "minimum-service-description",
            "recoveryMarginSeconds": 72000,
            "drivers": [
                {"driver": "mtpd", "level": "high", "value": "P1D"},
                {
                    "driver": "impact:integrity",
                    "level": "high",
                    "value": "high",
                },
            ],
        },
    )

    payload = projection.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert payload["entityRef"] == "component:default/fastapi-sample"
    assert payload["calculated"] == "high"
    assert payload["recoveryMarginSeconds"] == 72000


@pytest.mark.parametrize("duration", ["1h", "PT", "P", "tomorrow"])
def test_business_criticality_projection_rejects_invalid_duration_shape(
    duration: str,
) -> None:
    with pytest.raises(ValidationError):
        BusinessCriticalityProjection.model_validate(
            {
                "entityRef": "component:default/fastapi-sample",
                "calculated": "high",
                "declared": "high",
                "status": "provisional",
                "mtpd": duration,
                "rto": "PT4H",
                "mbco": "minimum-service-description",
                "recoveryMarginSeconds": 1,
                "drivers": [{"driver": "rto", "level": "high", "value": "PT4H"}],
            },
        )


def test_dependency_criticality_keeps_inherited_signal_separate() -> None:
    projection = DependencyCriticalityProjection.model_validate(
        {
            "entityRef": "resource:default/postgresql",
            "ownBusinessCriticality": None,
            "effectiveDependencyCriticality": "critical",
            "elevatedByDependencies": True,
            "inheritedFrom": ["component:default/fastapi-sample"],
        },
    )

    payload = projection.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert "ownBusinessCriticality" not in payload
    assert payload["effectiveDependencyCriticality"] == "critical"
    assert payload["inheritedFrom"] == ["component:default/fastapi-sample"]
