"""Validated settings for optional feature-flag integrations."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import Field, SecretStr, field_validator

from nabla.settings.base import SettingsBase


UNLEASH_DEFAULT_API_URL = "https://gitlab.com/api/v4/feature_flags/unleash/46788175"
_UNLEASH_PLACEHOLDER_CREDENTIALS = frozenset(
    {"", "xxx", "changeme", "change-me"},
)
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_TRUE_VALUES = frozenset({"", "1", "true", "yes", "on"})


def _optional_secret(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _optional_text(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _legacy_ssl_verify(value: object) -> object:
    """Preserve the historical permissive UNLEASH_SSL_VERIFY parsing."""
    if value is None or isinstance(value, bool):
        return True if value is None else value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _FALSE_VALUES:
            return False
        if normalized in _TRUE_VALUES:
            return True
        return True
    return value


class UnleashSettings(SettingsBase):
    """Typed Unleash configuration without import-time credential decisions."""

    unleash_api_url: str = UNLEASH_DEFAULT_API_URL
    unleash_app_name: str = "staging"
    unleash_instance_id: SecretStr | None = None
    unleash_refresh_interval: int = Field(default=60, ge=1, le=3600)
    unleash_metrics_interval: int = Field(default=90, ge=1, le=3600)
    unleash_request_timeout: int = Field(default=45, ge=1, le=300)
    unleash_request_retries: int = Field(default=4, ge=0, le=20)
    unleash_ssl_verify: bool = True
    unleash_ca_bundle: str | None = None
    unleash_disable_metrics: bool = False

    @field_validator("unleash_instance_id", mode="before")
    @classmethod
    def _normalize_instance_id(cls, value: object) -> object:
        return _optional_secret(value)

    @field_validator("unleash_ca_bundle", mode="before")
    @classmethod
    def _normalize_ca_bundle(cls, value: object) -> object:
        return _optional_text(value)

    @field_validator("unleash_ssl_verify", mode="before")
    @classmethod
    def _normalize_ssl_verify(cls, value: object) -> object:
        return _legacy_ssl_verify(value)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> UnleashSettings:
        """Build only from the supplied mapping, never from dotenv fallbacks."""
        return cls(
            unleash_api_url=values.get(
                "UNLEASH_API_URL",
                UNLEASH_DEFAULT_API_URL,
            ),
            unleash_app_name=values.get("UNLEASH_APP_NAME", "staging"),
            unleash_instance_id=values.get("UNLEASH_INSTANCE_ID", ""),
            unleash_refresh_interval=values.get("UNLEASH_REFRESH_INTERVAL", "60"),
            unleash_metrics_interval=values.get("UNLEASH_METRICS_INTERVAL", "90"),
            unleash_request_timeout=values.get("UNLEASH_REQUEST_TIMEOUT", "45"),
            unleash_request_retries=values.get("UNLEASH_REQUEST_RETRIES", "4"),
            unleash_ssl_verify=values.get("UNLEASH_SSL_VERIFY", "true"),
            unleash_ca_bundle=values.get("UNLEASH_CA_BUNDLE", ""),
            unleash_disable_metrics=values.get(
                "UNLEASH_DISABLE_METRICS",
                "false",
            ),
        )

    @property
    def instance_id(self) -> str:
        if self.unleash_instance_id is None:
            return ""
        return self.unleash_instance_id.get_secret_value().strip()

    @property
    def configured(self) -> bool:
<<<<<<< HEAD
        return (
            self.instance_id.casefold()
            not in _FEATURE_FLAG_PLACEHOLDER_CREDENTIALS
        )
=======
        return self.instance_id.casefold() not in _UNLEASH_PLACEHOLDER_CREDENTIALS
>>>>>>> 826fd02d (refactor: format [skip ci])

    @property
    def api_url(self) -> str:
        return self.unleash_api_url.rstrip("/")


class StatsigSettings(SettingsBase):
    """Typed Statsig configuration without import-time credential decisions."""

    statsig_api_key: SecretStr | None = None
    statsig_environment: str = "development"

    @field_validator("statsig_api_key", mode="before")
    @classmethod
    def _normalize_api_key(cls, value: object) -> object:
        return _optional_secret(value)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "StatsigSettings":
        """Build only from the supplied mapping, never from dotenv fallbacks."""
        return cls(
            statsig_api_key=values.get("STATSIG_API_KEY", ""),
            statsig_environment=values.get(
                "STATSIG_ENVIRONMENT",
                "development",
            ),
        )

    @property
    def api_key(self) -> str:
        if self.statsig_api_key is None:
            return ""
        return self.statsig_api_key.get_secret_value().strip()

    @property
    def configured(self) -> bool:
        return (
            self.api_key.casefold()
            not in _FEATURE_FLAG_PLACEHOLDER_CREDENTIALS
        )
