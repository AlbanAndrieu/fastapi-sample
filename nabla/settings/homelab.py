"""Validated settings for optional homelab control-plane providers."""

from __future__ import annotations

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
    def url(self) -> str:
        return self.truenas_url

    @property
    def verify_ssl(self) -> bool:
        return self.truenas_api_verify_ssl

    @property
    def websocket_path(self) -> str:
        return self.truenas_ws_path
