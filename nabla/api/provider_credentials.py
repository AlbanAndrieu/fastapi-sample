"""Sanitized environment credential checks for optional infrastructure providers."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re

_ENV_REFERENCE_RE = re.compile(r"[A-Z][A-Z0-9_]{2,}")


@dataclass(frozen=True, slots=True)
class ProviderCredentialStatus:
    """Describe provider configuration without retaining or returning secret values."""

    provider: str
    missing_variables: tuple[str, ...] = ()
    invalid_reference_variables: tuple[str, ...] = ()

    @property
    def configured(self) -> bool:
        return not self.missing_variables and not self.invalid_reference_variables

    @property
    def stage(self) -> str:
        if self.missing_variables:
            return "missing_credentials"
        if self.invalid_reference_variables:
            return "invalid_credential_reference"
        return "configured"

    def as_dict(self) -> dict[str, object]:
        """Return only variable names and state; never secret material."""
        return {
            "provider": self.provider,
            "configured": self.configured,
            "configuration_stage": self.stage,
            "missing_variables": list(self.missing_variables),
            "invalid_reference_variables": list(self.invalid_reference_variables),
        }


def inspect_environment_credentials(
    provider: str,
    *required_variables: str,
    secret_variables: frozenset[str] = frozenset(),
) -> ProviderCredentialStatus:
    """Validate required env-var presence and reject secret values that are env-var names."""
    missing: list[str] = []
    invalid_references: list[str] = []
    for name in required_variables:
        value = os.getenv(name, "").strip()
        if not value:
            missing.append(name)
            continue
        if name in secret_variables and _ENV_REFERENCE_RE.fullmatch(value):
            invalid_references.append(name)
    return ProviderCredentialStatus(
        provider=provider,
        missing_variables=tuple(missing),
        invalid_reference_variables=tuple(invalid_references),
    )
