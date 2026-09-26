"""Validated settings for observability integrations."""

from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator

from nabla.settings.base import SettingsBase

_ALLOWED_PROMETHEUS_SCHEMES = frozenset({"http", "https"})
_LOGFIRE_DEFAULT_BASE_URL = "https://logfire-api.pydantic.dev"
_LOGFIRE_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _optional_secret(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _legacy_logfire_bool(value: object) -> object:
    """Preserve historical Logfire env parsing for arbitrary string values."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in _LOGFIRE_FALSE_VALUES
    return value


class HomelabPrometheusSettings(SettingsBase):
    """Optional, read-only Prometheus query settings for the trusted LAN."""

    homelab_prometheus_url: str | None = None
    homelab_prometheus_timeout_seconds: float = Field(default=1.5, ge=0.2, le=5.0)

    @field_validator("homelab_prometheus_url", mode="before")
    @classmethod
    def _strip_optional_url(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("homelab_prometheus_url")
    @classmethod
    def _validate_prometheus_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme.casefold() not in _ALLOWED_PROMETHEUS_SCHEMES
            or not parsed.hostname
        ):
            raise ValueError(
                "HOMELAB_PROMETHEUS_URL must be an HTTP(S) URL with a host"
            )
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError(
                "HOMELAB_PROMETHEUS_URL must not contain credentials, query or fragment"
            )
        if parsed.path not in ("", "/"):
            raise ValueError("HOMELAB_PROMETHEUS_URL must not contain a path")
        return value.rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.homelab_prometheus_url)

    @property
    def base_url(self) -> str:
        return self.homelab_prometheus_url or ""


class LogfireSettings(SettingsBase):
    """Typed Logfire instrumentation settings without probe-only coupling."""

    logfire_enabled: bool | None = None
    logfire_token: SecretStr | None = None
    logfire_environment: str | None = None

    @field_validator("logfire_enabled", mode="before")
    @classmethod
    def _normalize_enabled(cls, value: object) -> object:
        return _legacy_logfire_bool(value)

    @field_validator("logfire_token", mode="before")
    @classmethod
    def _normalize_token(cls, value: object) -> object:
        return _optional_secret(value)

    @property
    def instrumentation_enabled(self) -> bool:
        """Match historical startup behavior: enabled unless explicitly false."""
        return self.logfire_enabled is not False

    @property
    def token(self) -> str:
        if self.logfire_token is None:
            return ""
        return self.logfire_token.get_secret_value().strip()


class LogfireProbeSettings(LogfireSettings):
    """Logfire health-probe settings, including legacy probe compatibility."""

    logfire_enable: bool | None = None
    logfire_base_url: str = _LOGFIRE_DEFAULT_BASE_URL

    @field_validator("logfire_enable", mode="before")
    @classmethod
    def _normalize_legacy_enabled(cls, value: object) -> object:
        return _legacy_logfire_bool(value)

    @field_validator("logfire_base_url", mode="before")
    @classmethod
    def _strip_base_url(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("logfire_base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("LOGFIRE_BASE_URL must be a valid HTTPS URL")
        return value

    @property
    def probe_enabled(self) -> bool:
        if self.logfire_enabled is not None:
            return self.logfire_enabled
        if self.logfire_enable is not None:
            return self.logfire_enable
        return bool(self.token)

    @property
    def probe_host(self) -> str:
        return urlsplit(self.logfire_base_url).hostname or ""

    @property
    def probe_port(self) -> int:
        return urlsplit(self.logfire_base_url).port or 443
