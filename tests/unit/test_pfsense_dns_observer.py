"""Tests for sanitized read-only pfSense DNS posture observation."""

import httpx
import pytest

from nabla.api import pfsense_dns_observer
from nabla.api.pfsense_dns_observer import PfSenseDNSSettings


@pytest.fixture

def settings() -> PfSenseDNSSettings:
    return PfSenseDNSSettings(
        base_url="https://pfsense.example.test",
        api_key="test-only-key",
        verify_ssl=True,
    )


def test_unconfigured_observer_is_unknown(monkeypatch) -> None:
    monkeypatch.delenv("PFSENSE_API_URL", raising=False)
    monkeypatch.delenv("PFSENSE_API_KEY", raising=False)

    result = pytest.run(asyncio=pfsense_dns_observer.observe_pfsense_dns_posture())

    assert result == {
        "configured": False,
        "reachable": None,
        "policy_state": "unknown",
        "reason": "pfSense API observation is not configured",
    }


@pytest.mark.asyncio
async def test_recursive_unbound_is_independent_and_green(monkeypatch, settings) -> None:
    async def fake_get_data(_client, path: str):
        return {
            "/api/v2/status/system": {"platform": "pfSense"},
            "/api/v2/status/services": [
                {"name": "unbound", "description": "DNS Resolver", "status": "running"}
            ],
            "/api/v2/services/dns_resolver/settings": {
                "enable": True,
                "forwarding": False,
                "forward_tls_upstream": False,
                "port": 53,
            },
            "/api/v2/system/dns": {"dnsserver": ["172.17.0.24"]},
        }[path]

    monkeypatch.setattr(pfsense_dns_observer, "_get_data", fake_get_data)

    result = await pfsense_dns_observer.observe_pfsense_dns_posture(
        settings=settings,
        truenas_hosts=frozenset({"172.17.0.24"}),
    )

    assert result["policy_state"] == "ok"
    assert result["resolver"]["enabled"] is True
    assert result["resolver"]["running"] is True
    assert result["resolver"]["forwarding"] is False
    assert result["upstream"]["independent_from_truenas"] is True
    assert result["upstream"]["truenas_only"] is False


@pytest.mark.asyncio
async def test_forwarding_only_to_truenas_is_warning(monkeypatch, settings) -> None:
    async def fake_get_data(_client, path: str):
        return {
            "/api/v2/status/system": {"platform": "pfSense"},
            "/api/v2/status/services": [{"service": "unbound", "running": True}],
            "/api/v2/services/dns_resolver/settings": {
                "enable": True,
                "forwarding": True,
                "forward_tls_upstream": False,
                "port": "53",
            },
            "/api/v2/system/dns": {"dnsserver": ["172.17.0.24"]},
        }[path]

    monkeypatch.setattr(pfsense_dns_observer, "_get_data", fake_get_data)

    result = await pfsense_dns_observer.observe_pfsense_dns_posture(
        settings=settings,
        truenas_hosts=frozenset({"172.17.0.24"}),
    )

    assert result["policy_state"] == "warn"
    assert result["upstream"]["independent_from_truenas"] is False
    assert result["upstream"]["truenas_only"] is True
    assert "TrueNAS" in result["reason"]


@pytest.mark.asyncio
async def test_stopped_unbound_is_failure(monkeypatch, settings) -> None:
    async def fake_get_data(_client, path: str):
        return {
            "/api/v2/status/system": {"platform": "pfSense"},
            "/api/v2/status/services": [{"name": "unbound", "status": "stopped"}],
            "/api/v2/services/dns_resolver/settings": {
                "enable": True,
                "forwarding": False,
            },
            "/api/v2/system/dns": {"dnsserver": []},
        }[path]

    monkeypatch.setattr(pfsense_dns_observer, "_get_data", fake_get_data)

    result = await pfsense_dns_observer.observe_pfsense_dns_posture(settings=settings)

    assert result["policy_state"] == "fail"
    assert result["resolver"]["running"] is False


def test_http_errors_are_redacted() -> None:
    request = httpx.Request("GET", "https://172.17.0.1/api/v2/status/system")
    response = httpx.Response(403, request=request)
    error = httpx.HTTPStatusError("forbidden", request=request, response=response)

    assert pfsense_dns_observer._safe_error(error) == "HTTP 403"
