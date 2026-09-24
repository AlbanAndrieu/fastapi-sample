"""Tests for typed health/runtime cache settings."""

import pytest

from nabla.api import health_board, homelab_runtime
from nabla.settings.health_runtime import HealthRuntimeSettings


def test_health_runtime_settings_preserve_environment_names(monkeypatch) -> None:
    monkeypatch.setenv("HEALTH_BOARD_CACHE_TTL_SECONDS", "45")
    monkeypatch.setenv("TRUENAS_RUNTIME_CACHE_TTL_SECONDS", "60")

    settings = HealthRuntimeSettings()

    assert settings.health_board_cache_ttl_seconds == 45.0
    assert settings.truenas_runtime_cache_ttl_seconds == 60.0
    assert health_board._ttl_seconds() == 45.0
    assert homelab_runtime._runtime_cache_ttl_seconds() == 60.0


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("health_board_cache_ttl_seconds", "", 30.0),
        ("health_board_cache_ttl_seconds", "invalid", 30.0),
        ("health_board_cache_ttl_seconds", "nan", 30.0),
        ("health_board_cache_ttl_seconds", "1", 10.0),
        ("health_board_cache_ttl_seconds", "999", 300.0),
        ("truenas_runtime_cache_ttl_seconds", "", 30.0),
        ("truenas_runtime_cache_ttl_seconds", "invalid", 30.0),
        ("truenas_runtime_cache_ttl_seconds", "inf", 30.0),
        ("truenas_runtime_cache_ttl_seconds", "1", 5.0),
        ("truenas_runtime_cache_ttl_seconds", "999", 300.0),
    ],
)
def test_health_runtime_settings_preserve_bounded_legacy_semantics(
    field: str,
    value: str,
    expected: float,
) -> None:
    settings = HealthRuntimeSettings(**{field: value})

    assert getattr(settings, field) == expected
