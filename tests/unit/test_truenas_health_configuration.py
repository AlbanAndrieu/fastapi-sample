"""TrueNAS health configuration must fail closed without leaking secret values."""

import pytest

from nabla.api import homelab_health


def _set_username(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRUENAS_USER", "albandrieu")
    monkeypatch.delenv("TRUENAS_API_USERNAME", raising=False)
    monkeypatch.delenv("TRUENAS_USERNAME", raising=False)


@pytest.mark.asyncio
async def test_missing_canonical_api_key_is_explicit_authentication_failure(monkeypatch) -> None:
    _set_username(monkeypatch)
    monkeypatch.delenv("TRUENAS_API_KEY", raising=False)
    monkeypatch.setenv("TRUENAS_MCP_API_KEY", "unused-mcp-placeholder")

    result = await homelab_health._observe_truenas_api()

    assert result["reachable"] is False
    assert result["phase"] == "authentication"
    assert result["stage"] == "missing_api_key"
    assert result["api_key_configured"] is False
    assert "TRUENAS_API_KEY" in result["error"]
    assert "unused-mcp-placeholder" not in result["error"]


@pytest.mark.asyncio
async def test_variable_name_in_api_key_is_rejected_without_echoing_value(monkeypatch) -> None:
    _set_username(monkeypatch)
    monkeypatch.setenv("TRUENAS_API_KEY", "PFSENSE_API_KEY")

    result = await homelab_health._observe_truenas_api()

    assert result["reachable"] is False
    assert result["phase"] == "authentication"
    assert result["stage"] == "invalid_api_key_reference"
    assert result["api_key_configured"] is True
    assert "environment-variable name" in result["error"]
    assert "PFSENSE_API_KEY" not in result["error"]


@pytest.mark.asyncio
async def test_malformed_raw_api_key_is_rejected_before_official_client(monkeypatch) -> None:
    _set_username(monkeypatch)
    monkeypatch.setenv("TRUENAS_API_KEY", "not-a-truenas-key")

    result = await homelab_health._observe_truenas_api()

    assert result["stage"] == "invalid_api_key_format"
    assert result["reachable"] is False
    assert "64-character-alphanumeric" in result["error"]


def test_canonical_api_key_accepts_truenas_26_raw_key_format(monkeypatch) -> None:
    from nabla.api import truenas_health_observer

    monkeypatch.setenv("TRUENAS_API_USERNAME", "fastapi_observer")
    monkeypatch.delenv("TRUENAS_USERNAME", raising=False)
    monkeypatch.delenv("TRUENAS_USER", raising=False)
    monkeypatch.setenv("TRUENAS_API_KEY", "8-" + ("A" * 64))

    assert truenas_health_observer.truenas_api_configuration_failure() is None


def test_failure_kind_classifies_truenas_ui_allowlist_denial() -> None:
    from nabla.api import truenas_health_observer

    phase, stage = truenas_health_observer._failure_kind(
        RuntimeError(
            "WebSocket connection closed with code=1008, "
            "reason='You are not allowed to access this resource'"
        )
    )

    assert phase == "connect"
    assert stage == "source_allowlist"


