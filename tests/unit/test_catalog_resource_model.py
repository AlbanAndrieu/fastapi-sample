"""Contract tests for catalog cutover identity and condition primitives."""

import pytest
from pydantic import ValidationError

from nabla.api.catalog_resource_model import (
    BackstageEntityRef,
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
        "component:default/cartography_ui",
    ],
)
def test_backstage_entity_ref_rejects_ambiguous_or_noncanonical_refs(
    value: str,
) -> None:
    with pytest.raises(ValidationError):
        BackstageEntityRef.model_validate(value)


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
