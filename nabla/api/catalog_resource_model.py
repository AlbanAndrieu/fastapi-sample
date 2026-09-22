"""Source-agnostic identity and condition primitives for the catalog cutover.

This module deliberately does not fetch or translate either catalog schema. It
contains only read-model primitives that can survive the one-shot replacement
of the legacy flat catalog with Backstage/provider-native resources.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator

ConditionStatus = Literal["True", "False", "Unknown"]
ReconciliationState = Literal[
    "in_sync",
    "declared_only",
    "observed_only",
    "binding_conflict",
    "runtime_unknown",
    "not_observed",
]

_ENTITY_REF_PATTERN = re.compile(
    r"^(component|resource|api|system|domain|group|user):"
    r"[a-z0-9][a-z0-9._-]*/[a-z0-9]+(?:-[a-z0-9]+)*$",
)


class BackstageEntityRef(RootModel[str]):
    """Canonical full Backstage entity reference used as a stable join key."""

    root: str = Field(min_length=1, max_length=255)

    @field_validator("root")
    @classmethod
    def validate_full_ref(cls, value: str) -> str:
        """Require an explicit kind, namespace and stable kebab-case name."""
        if _ENTITY_REF_PATTERN.fullmatch(value) is None:
            raise ValueError(
                "entity ref must be a full lowercase Backstage ref "
                "(<kind>:<namespace>/<kebab-name>)",
            )
        return value

    @property
    def kind(self) -> str:
        """Return the canonical entity kind."""
        return self.root.partition(":")[0]

    @property
    def namespace(self) -> str:
        """Return the canonical entity namespace."""
        remainder = self.root.partition(":")[2]
        return remainder.partition("/")[0]

    @property
    def name(self) -> str:
        """Return the stable entity name."""
        return self.root.rpartition("/")[2]


class CatalogCondition(BaseModel):
    """Kubernetes-style condition for reconciled catalog/runtime resources."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )

    type: str = Field(min_length=1, max_length=80)
    status: ConditionStatus
    reason: str = Field(min_length=1, max_length=80, pattern=r"^[A-Z][A-Za-z0-9]*$")
    message: str | None = Field(default=None, max_length=512)
    last_transition_time: datetime | None = Field(
        default=None,
        validation_alias="lastTransitionTime",
        serialization_alias="lastTransitionTime",
    )


_RECONCILIATION_CONDITIONS: dict[
    ReconciliationState,
    tuple[ConditionStatus, str, str],
] = {
    "in_sync": (
        "True",
        "InSync",
        "Declared runtime identity matches one observed provider resource.",
    ),
    "declared_only": (
        "False",
        "DeclaredOnly",
        "Declared service has no matching observed provider resource.",
    ),
    "observed_only": (
        "False",
        "ObservedOnly",
        "Observed provider resource has no declared catalog identity.",
    ),
    "binding_conflict": (
        "False",
        "BindingConflict",
        "Declared runtime identity matches multiple observed provider resources.",
    ),
    "runtime_unknown": (
        "Unknown",
        "RuntimeUnavailable",
        "Runtime provider could not be observed.",
    ),
    "not_observed": (
        "Unknown",
        "ObservationNotApplicable",
        "This declaration is not observed by the selected runtime provider.",
    ),
}


def reconciliation_condition(state: ReconciliationState) -> CatalogCondition:
    """Map the legacy reconciliation enum to the future resource condition form."""
    status, reason, message = _RECONCILIATION_CONDITIONS[state]
    return CatalogCondition(
        type="Reconciled",
        status=status,
        reason=reason,
        message=message,
    )
