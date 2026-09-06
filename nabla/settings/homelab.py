"""Validated settings for optional homelab control-plane providers."""

from __future__ import annotations

import os
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator

from nabla.settings.base import SettingsBase

DEFAULT_TRUENAS_URL = "https://truenas.albandrieu.com:7000"
DEFAULT_TRUENAS_WS_PATH = "/api/current"
_ALLOWED_TRUENAS_SCHEMES = frozenset({"http", "https", "ws", "wss"})


class TrueNASProviderSettings(SettingsBase):
    """Environment-backed TrueNAS settings with explicit compatibility aliases.

    The canonical health contract intentionally requires ``TRUENAS_API_KEY``.
    The lower-level adapter may additionally reuse ``TRUENAS_MCP_API_KEY`` for
    backwards compatibility. Keeping both values explicit prevents a fallback
    secret from silently changing the health/configuration contract.
    """

    truenas_url: str = DEFAULT_TRUENAS_URL
    truenas_api_username: str | None = None
    truenas_username: str | None = None
    truenas_user: str | None = None
    truenas_api_key: SecretStr | None = None
    truenas_mcp_api_key: SecretStr | None = None
    truenas_api_verify_ssl: bool = True
    truenas_ws_path: str = DEFAULT_TRUENAS_WS_PATH

    @field_validator(
        "truenas_api_username",
        "truenas_username",
        "truenas_user",
        mode="before",
    )
    @classmethod
    def _strip_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("truenas_api_key", "truenas_mcp_api_key", mode="before")
    @classmethod
    def _strip_optional_secret(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("truenas_url", mode="before")
    @classmethod
    def _default_blank_url(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or DEFAULT_TRUENAS_URL
        return value

    @field_validator("truenas_url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        valid_scheme = parsed.scheme.casefold() in _ALLOWED_TRUENAS_SCHEMES
        if not valid_scheme or not parsed.hostname:
            raise ValueError(
                "TRUENAS_URL must be an HTTP(S) or WS(S) URL with a host"
            )
        return value

    @field_validator("truenas_api_verify_ssl", mode="before")
    @classmethod
    def _preserve_blank_tls_compatibility(cls, value: object) -> object:
        # Historical parsing treated an explicitly blank value as disabled.
        if isinstance(value, str) and not value.strip():
            return False
        return value

    @field_validator("truenas_ws_path", mode="before")
    @classmethod
    def _normalize_websocket_path(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        path = value.strip()
        if not path:
            return DEFAULT_TRUENAS_WS_PATH
        return "/" + path.lstrip("/")

    @staticmethod
    def _secret_value(secret: SecretStr | None) -> str:
        return secret.get_secret_value().strip() if secret is not None else ""

    @property
    def adapter_username(self) -> str:
        """Return the supported username aliases in historical precedence order."""
        return (
            self.truenas_api_username
            or self.truenas_username
            or self.truenas_user
            or ""
        )

    @property
    def adapter_username_environment(self) -> str:
        """Return the selected username variable name without its value."""
        if self.truenas_api_username:
            return "TRUENAS_API_USERNAME"
        if self.truenas_username:
            return "TRUENAS_USERNAME"
        if self.truenas_user:
            return "TRUENAS_USER"
        return "TRUENAS_API_USERNAME"

    @property
    def shadowed_username_environments(self) -> tuple[str, ...]:
        """Return configured lower-priority username aliases that are ignored."""
        selected = self.adapter_username_environment
        configured = (
            ("TRUENAS_API_USERNAME", self.truenas_api_username),
            ("TRUENAS_USERNAME", self.truenas_username),
            ("TRUENAS_USER", self.truenas_user),
        )
        return tuple(name for name, value in configured if value and name != selected)

    @property
    def canonical_api_key(self) -> str:
        """Return only the canonical health API key."""
        return self._secret_value(self.truenas_api_key)

    @property
    def adapter_api_key(self) -> str:
        """Return the adapter key with the legacy MCP fallback preserved."""
        return self.canonical_api_key or self._secret_value(self.truenas_mcp_api_key)

    @property
    def adapter_api_key_environment(self) -> str:
        """Return the selected adapter key variable name without its value."""
        if self.canonical_api_key:
            return "TRUENAS_API_KEY"
        if self._secret_value(self.truenas_mcp_api_key):
            return "TRUENAS_MCP_API_KEY"
        return "TRUENAS_API_KEY"

    @property
    def shadowed_api_key_environments(self) -> tuple[str, ...]:
        """Return configured lower-priority API-key aliases that are ignored."""
        if self.canonical_api_key and self._secret_value(self.truenas_mcp_api_key):
            return ("TRUENAS_MCP_API_KEY",)
        return ()

    @property
    def url(self) -> str:
        return self.truenas_url

    @property
    def verify_ssl(self) -> bool:
        return self.truenas_api_verify_ssl

    @property
    def websocket_path(self) -> str:
        return self.truenas_ws_path


_ALLOWED_PFSENSE_SCHEMES = frozenset({"http", "https"})


def _pfsense_optional_text(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _pfsense_optional_secret(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _pfsense_optional_tls(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _pfsense_shared_tls(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return True
    return value


def _pfsense_url(value: str | None, *, variable: str) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    if parsed.scheme.casefold() not in _ALLOWED_PFSENSE_SCHEMES or not parsed.hostname:
        raise ValueError(f"{variable} must be an HTTP(S) URL with a host")
    return value.rstrip("/")


def _secret_value(secret: SecretStr | None) -> str:
    return secret.get_secret_value().strip() if secret is not None else ""


def pfsense_posture_environment_variables() -> tuple[str, str]:
    """Return the selected posture URL/key variable names without secret values."""
    url_var = (
        "PFSENSE_POSTURE_API_URL"
        if os.getenv("PFSENSE_POSTURE_API_URL", "").strip()
        else "PFSENSE_API_URL"
    )
    if os.getenv("PFSENSE_POSTURE_API_KEY", "").strip():
        key_var = "PFSENSE_POSTURE_API_KEY"
    elif os.getenv("PFSENSE_API_KEY", "").strip():
        key_var = "PFSENSE_API_KEY"
    else:
        key_var = "PFSENSE_POSTURE_API_KEY"
    return url_var, key_var


def pfsense_security_environment_variables() -> tuple[str, str]:
    """Return the selected security URL/key variable names without secret values."""
    url_var = (
        "PFSENSE_SECURITY_API_URL"
        if os.getenv("PFSENSE_SECURITY_API_URL", "").strip()
        else "PFSENSE_API_URL"
    )
    if os.getenv("PFSENSE_SECURITY_API_KEY", "").strip():
        key_var = "PFSENSE_SECURITY_API_KEY"
    elif os.getenv("PFSENSE_API_KEY", "").strip():
        key_var = "PFSENSE_API_KEY"
    else:
        key_var = "PFSENSE_SECURITY_API_KEY"
    return url_var, key_var


class _PfSenseSharedProviderSettings(SettingsBase):
    """Shared compatibility transport inherited by split pfSense identities."""

    pfsense_api_url: str | None = None
    pfsense_api_key: SecretStr | None = None
    pfsense_api_verify_ssl: bool = True

    @field_validator("pfsense_api_url", mode="before")
    @classmethod
    def _strip_shared_url(cls, value: object) -> object:
        return _pfsense_optional_text(value)

    @field_validator("pfsense_api_url")
    @classmethod
    def _validate_shared_url(cls, value: str | None) -> str | None:
        return _pfsense_url(value, variable="PFSENSE_API_URL")

    @field_validator("pfsense_api_key", mode="before")
    @classmethod
    def _strip_shared_secret(cls, value: object) -> object:
        return _pfsense_optional_secret(value)

    @field_validator("pfsense_api_verify_ssl", mode="before")
    @classmethod
    def _normalize_shared_tls(cls, value: object) -> object:
        return _pfsense_shared_tls(value)


class PfSensePostureProviderSettings(_PfSenseSharedProviderSettings):
    """Validated read-only pfSense posture transport settings."""

    pfsense_posture_api_url: str | None = None
    pfsense_posture_api_key: SecretStr | None = None
    pfsense_posture_api_verify_ssl: bool | None = None

    @field_validator("pfsense_posture_api_url", mode="before")
    @classmethod
    def _strip_posture_url(cls, value: object) -> object:
        return _pfsense_optional_text(value)

    @field_validator("pfsense_posture_api_url")
    @classmethod
    def _validate_posture_url(cls, value: str | None) -> str | None:
        return _pfsense_url(value, variable="PFSENSE_POSTURE_API_URL")

    @field_validator("pfsense_posture_api_key", mode="before")
    @classmethod
    def _strip_posture_secret(cls, value: object) -> object:
        return _pfsense_optional_secret(value)

    @field_validator("pfsense_posture_api_verify_ssl", mode="before")
    @classmethod
    def _normalize_posture_tls(cls, value: object) -> object:
        return _pfsense_optional_tls(value)

    @property
    def base_url(self) -> str:
        return self.pfsense_posture_api_url or self.pfsense_api_url or ""

    @property
    def api_key(self) -> str:
        return _secret_value(self.pfsense_posture_api_key) or _secret_value(
            self.pfsense_api_key
        )

    @property
    def verify_ssl(self) -> bool:
        if self.pfsense_posture_api_verify_ssl is not None:
            return self.pfsense_posture_api_verify_ssl
        return self.pfsense_api_verify_ssl

    @property
    def credential_mode(self) -> str:
        return (
            "dedicated_posture"
            if _secret_value(self.pfsense_posture_api_key)
            else "legacy_shared"
        )


class PfSenseSecurityProviderSettings(_PfSenseSharedProviderSettings):
    """Validated least-privilege pfSense security telemetry settings."""

    pfsense_security_api_url: str | None = None
    pfsense_security_api_key: SecretStr | None = None
    pfsense_security_api_verify_ssl: bool | None = None
    pfsense_security_path_mode: Literal["shared_wan", "out_of_band"] = "shared_wan"

    @field_validator("pfsense_security_api_url", mode="before")
    @classmethod
    def _strip_security_url(cls, value: object) -> object:
        return _pfsense_optional_text(value)

    @field_validator("pfsense_security_api_url")
    @classmethod
    def _validate_security_url(cls, value: str | None) -> str | None:
        return _pfsense_url(value, variable="PFSENSE_SECURITY_API_URL")

    @field_validator("pfsense_security_api_key", mode="before")
    @classmethod
    def _strip_security_secret(cls, value: object) -> object:
        return _pfsense_optional_secret(value)

    @field_validator("pfsense_security_api_verify_ssl", mode="before")
    @classmethod
    def _normalize_security_tls(cls, value: object) -> object:
        return _pfsense_optional_tls(value)

    @field_validator("pfsense_security_path_mode", mode="before")
    @classmethod
    def _normalize_security_path_mode(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip().lower()
            return stripped or "shared_wan"
        return value

    @property
    def base_url(self) -> str:
        return self.pfsense_security_api_url or self.pfsense_api_url or ""

    @property
    def api_key(self) -> str:
        return _secret_value(self.pfsense_security_api_key) or _secret_value(
            self.pfsense_api_key
        )

    @property
    def verify_ssl(self) -> bool:
        if self.pfsense_security_api_verify_ssl is not None:
            return self.pfsense_security_api_verify_ssl
        return self.pfsense_api_verify_ssl

    @property
    def credential_mode(self) -> str:
        return (
            "dedicated_security"
            if _secret_value(self.pfsense_security_api_key)
            else "legacy_shared"
        )

    @property
    def control_path_mode(self) -> Literal["shared_wan", "out_of_band"]:
        return self.pfsense_security_path_mode


def pfsense_invalid_configuration_variables(exc: Exception) -> list[str]:
    """Return only failing environment variable names from a Pydantic error."""
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return []
    variables: set[str] = set()
    for error in errors():
        location = error.get("loc")
        if isinstance(location, tuple) and location:
            variables.add(str(location[-1]).upper())
    return sorted(variables)
