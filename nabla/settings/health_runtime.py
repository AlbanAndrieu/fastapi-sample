"""Typed settings for bounded health and homelab runtime caches."""

from __future__ import annotations

import math

from pydantic import field_validator

from nabla.settings.base import SettingsBase

_DEFAULT_HEALTH_BOARD_CACHE_TTL_SECONDS = 30.0
_MIN_HEALTH_BOARD_CACHE_TTL_SECONDS = 10.0
_MAX_HEALTH_BOARD_CACHE_TTL_SECONDS = 300.0

_DEFAULT_TRUENAS_RUNTIME_CACHE_TTL_SECONDS = 30.0
_MIN_TRUENAS_RUNTIME_CACHE_TTL_SECONDS = 5.0
_MAX_TRUENAS_RUNTIME_CACHE_TTL_SECONDS = 300.0


def _bounded_float(
    value: object,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    """Preserve legacy fallback/clamping while centralizing typed parsing."""
    if isinstance(value, str) and not value.strip():
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return max(minimum, min(parsed, maximum))


class HealthRuntimeSettings(SettingsBase):
    """Environment-backed cache settings for health/runtime snapshots."""

    health_board_cache_ttl_seconds: float = _DEFAULT_HEALTH_BOARD_CACHE_TTL_SECONDS
    truenas_runtime_cache_ttl_seconds: float = _DEFAULT_TRUENAS_RUNTIME_CACHE_TTL_SECONDS

    @field_validator("health_board_cache_ttl_seconds", mode="before")
    @classmethod
    def _normalize_health_board_cache_ttl(cls, value: object) -> float:
        return _bounded_float(
            value,
            default=_DEFAULT_HEALTH_BOARD_CACHE_TTL_SECONDS,
            minimum=_MIN_HEALTH_BOARD_CACHE_TTL_SECONDS,
            maximum=_MAX_HEALTH_BOARD_CACHE_TTL_SECONDS,
        )

    @field_validator("truenas_runtime_cache_ttl_seconds", mode="before")
    @classmethod
    def _normalize_truenas_runtime_cache_ttl(cls, value: object) -> float:
        return _bounded_float(
            value,
            default=_DEFAULT_TRUENAS_RUNTIME_CACHE_TTL_SECONDS,
            minimum=_MIN_TRUENAS_RUNTIME_CACHE_TTL_SECONDS,
            maximum=_MAX_TRUENAS_RUNTIME_CACHE_TTL_SECONDS,
        )
