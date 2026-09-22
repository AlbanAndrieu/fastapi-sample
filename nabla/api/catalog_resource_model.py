"""Source-agnostic identity and condition primitives for the catalog cutover.

This module deliberately does not fetch or translate either catalog schema. It
contains only read-model primitives that can survive the one-shot replacement
of the legacy flat catalog with Backstage/provider-native resources.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator

ConditionStatus = Literal["True", "False", "Unknown"]
CriticalityLevel = Literal["low", "medium", "high", "critical"]
BiaAssessmentStatus = Literal["provisional", "validated"]
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
_ISO8601_DURATION_PATTERN = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$",
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
    reason: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Z][A-Za-z0-9]*$",
    )
    message: str | None = Field(default=None, max_length=512)
    last_transition_time: datetime | None = Field(
        default=None,
        validation_alias="lastTransitionTime",
        serialization_alias="lastTransitionTime",
    )


class BusinessCriticalityDriver(BaseModel):
    """One authoritative driver emitted by the nabla-compose BIA policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    driver: str = Field(min_length=1, max_length=80)
    level: CriticalityLevel
    value: str = Field(min_length=1, max_length=128)


class BusinessCriticalityProjection(BaseModel):
    """Calculated BIA projection consumed from nabla-compose without recomputation."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    entity_ref: BackstageEntityRef = Field(
        validation_alias="entityRef",
        serialization_alias="entityRef",
    )
    calculated: CriticalityLevel
    declared: CriticalityLevel | None = None
    status: BiaAssessmentStatus
    mtpd: str = Field(min_length=1, max_length=32)
    rto: str = Field(min_length=1, max_length=32)
    rpo: str | None = Field(default=None, min_length=1, max_length=32)
    mbco: str = Field(min_length=1, max_length=512)
    recovery_margin_seconds: int = Field(
        gt=0,
        validation_alias="recoveryMarginSeconds",
        serialization_alias="recoveryMarginSeconds",
    )
    drivers: list[BusinessCriticalityDriver] = Field(min_length=1)

    @field_validator("mtpd", "rto", "rpo")
    @classmethod
    def validate_duration_shape(cls, value: str | None) -> str | None:
        """Fail closed on malformed projected durations without recalculating tiers."""
        if value is None:
            return None
        match = _ISO8601_DURATION_PATTERN.fullmatch(value)
        if match is None or not any(match.groupdict().values()):
            raise ValueError("BIA duration must use the bounded ISO-8601 syntax")
        if "T" in value and not any(
            match.group(key) for key in ("hours", "minutes", "seconds")
        ):
            raise ValueError("BIA duration must use the bounded ISO-8601 syntax")
        return value


class DependencyCriticalityProjection(BaseModel):
    """Derived dependency amplification kept separate from an entity's own BIA."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    entity_ref: BackstageEntityRef = Field(
        validation_alias="entityRef",
        serialization_alias="entityRef",
    )
    own_business_criticality: CriticalityLevel | None = Field(
        default=None,
        validation_alias="ownBusinessCriticality",
        serialization_alias="ownBusinessCriticality",
    )
    effective_dependency_criticality: CriticalityLevel | None = Field(
        default=None,
        validation_alias="effectiveDependencyCriticality",
        serialization_alias="effectiveDependencyCriticality",
    )
    elevated_by_dependencies: bool = Field(
        validation_alias="elevatedByDependencies",
        serialization_alias="elevatedByDependencies",
    )
    inherited_from: list[BackstageEntityRef] = Field(
        default_factory=list,
        validation_alias="inheritedFrom",
        serialization_alias="inheritedFrom",
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
