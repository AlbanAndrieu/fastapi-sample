"""Validated settings for read-only homelab observability queries."""

from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import Field, field_validator

from nabla.settings.base import SettingsBase

_ALLOWED_PROMETHEUS_SCHEMES = frozenset({"http", "https"})


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
        return value.rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.homelab_prometheus_url)

    @property
    def base_url(self) -> str:
        return self.homelab_prometheus_url or ""
