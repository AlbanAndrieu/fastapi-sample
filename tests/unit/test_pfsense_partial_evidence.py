"""Regression coverage for partial read-only pfSense posture evidence."""

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


async def _security_clear():
    return {
        "state": "clear",
        "engine": "snort",
        "mechanism": "snort2c",
    }


@pytest.mark.asyncio
async def test_system_502_does_not_hide_service_or_unbound_evidence(
    monkeypatch,
    settings,
) -> None:
    async def fake_get_data(_client, path: str):
        if path == "/api/v2/system/version":
            request = httpx.Request("GET", "https://pfsense.example.test/api/v2/system/version")
            response = httpx.Response(502, request=request)
            raise httpx.HTTPStatusError(
                "bad gateway",
                request=request,
                response=response,
            )
        return {
            "/api/v2/status/services": [
                {"name": "unbound", "description": "DNS Resolver", "status": "running"},
                {"name": "snort_wan", "description": "Snort IDS", "status": "running"},
                {"name": "crowdsec", "description": "CrowdSec", "status": "stopped"},
            ],
            "/api/v2/services/dns_resolver/settings": {
                "enable": True,
                "forwarding": False,
                "forward_tls_upstream": False,
                "port": 53,
            },
            "/api/v2/system/dns": {"dnsserver": []},
        }[path]

    monkeypatch.setattr(pfsense_dns_observer, "_get_data", fake_get_data)
    monkeypatch.setattr(
        pfsense_dns_observer,
        "observe_pfsense_ingress_block",
        _security_clear,
    )

    result = await pfsense_dns_observer.observe_pfsense_dns_posture(
        settings=settings,
    )

    assert result["reachable"] is True
    assert result["api_evidence_state"] == "partial"
    assert result["error_stage"] == "system"
    assert result["error"] == "HTTP 502"
    assert result["endpoint_status"]["system"] == {
        "observed": False,
        "error": "HTTP 502",
    }
    assert result["endpoint_status"]["services"] == {"observed": True}
    assert result["services_observed"] is True
    assert result["resolver"]["running"] is True
    assert result["resolver"]["enabled"] is True
    assert result["policy_state"] == "ok"
    assert result["service_summary"] == {
        "running": 2,
        "stopped": 1,
        "unknown": 0,
        "total": 3,
    }

    filters = {row["id"]: row for row in result["security_filters"]}
    assert filters["snort"]["state"] == "running"
    assert filters["pfblockerng"]["state"] == "not_observed"
    assert filters["crowdsec"]["state"] == "stopped"


@pytest.mark.asyncio
async def test_failed_service_inventory_is_unknown_not_not_observed(
    monkeypatch,
    settings,
) -> None:
    async def fake_get_data(_client, path: str):
        if path == "/api/v2/status/services":
            request = httpx.Request("GET", "https://pfsense.example.test/api/v2/status/services")
            raise httpx.ReadTimeout("slow", request=request)
        return {
            "/api/v2/system/version": {"version": "2.8.0"},
            "/api/v2/services/dns_resolver/settings": {
                "enable": True,
                "forwarding": False,
            },
            "/api/v2/system/dns": {"dnsserver": []},
        }[path]

    monkeypatch.setattr(pfsense_dns_observer, "_get_data", fake_get_data)
    monkeypatch.setattr(
        pfsense_dns_observer,
        "observe_pfsense_ingress_block",
        _security_clear,
    )

    result = await pfsense_dns_observer.observe_pfsense_dns_posture(
        settings=settings,
    )

    assert result["services_observed"] is False
    filters = {row["id"]: row for row in result["security_filters"]}
    assert filters["pfblockerng"]["state"] == "unknown"
    assert filters["crowdsec"]["state"] == "unknown"
    assert "did not succeed" in filters["pfblockerng"]["detail"]
