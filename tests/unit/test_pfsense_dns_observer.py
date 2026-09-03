"""Tests for sanitized read-only pfSense DNS posture observation."""

import asyncio

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


async def _security_unavailable():
    return {
        "state": "telemetry_unavailable",
        "engine": "snort",
        "mechanism": "snort2c",
    }


async def _security_clear():
    return {
        "state": "clear",
        "engine": "snort",
        "mechanism": "snort2c",
    }


@pytest.mark.asyncio
async def test_unconfigured_observer_is_unknown(monkeypatch) -> None:
    monkeypatch.delenv("PFSENSE_API_URL", raising=False)
    monkeypatch.delenv("PFSENSE_API_KEY", raising=False)
    monkeypatch.delenv("PFSENSE_POSTURE_API_URL", raising=False)
    monkeypatch.delenv("PFSENSE_POSTURE_API_KEY", raising=False)
    monkeypatch.setattr(
        pfsense_dns_observer,
        "observe_pfsense_ingress_block",
        _security_unavailable,
    )

    result = await pfsense_dns_observer.observe_pfsense_dns_posture()

    assert result["configured"] is False
    assert result["reachable"] is None
    assert result["policy_state"] == "unknown"
    assert result["configuration_stage"] == "missing_credentials"
    assert result["missing_variables"] == [
        "PFSENSE_API_URL",
        "PFSENSE_POSTURE_API_KEY",
    ]
    assert result["ingress_block"]["state"] == "telemetry_unavailable"
    assert isinstance(result["security_filters"], list)


@pytest.mark.asyncio
async def test_pfsense_api_key_reference_is_rejected_without_echoing_value(monkeypatch) -> None:
    monkeypatch.setenv("PFSENSE_API_URL", "https://pfsense.example.test")
    monkeypatch.setenv("PFSENSE_API_KEY", "TRUENAS_API_KEY")
    monkeypatch.delenv("PFSENSE_POSTURE_API_KEY", raising=False)
    monkeypatch.setattr(
        pfsense_dns_observer,
        "observe_pfsense_ingress_block",
        _security_unavailable,
    )

    result = await pfsense_dns_observer.observe_pfsense_dns_posture()

    assert result["configured"] is False
    assert result["configuration_stage"] == "invalid_credential_reference"
    assert result["invalid_reference_variables"] == ["PFSENSE_API_KEY"]
    assert "TRUENAS_API_KEY" not in repr(result)


def test_dedicated_posture_credentials_are_preferred(monkeypatch) -> None:
    monkeypatch.setenv("PFSENSE_API_URL", "https://pfsense.example.test")
    monkeypatch.setenv("PFSENSE_API_KEY", "narrow-security-key")
    monkeypatch.setenv("PFSENSE_POSTURE_API_KEY", "posture-read-key")

    status = pfsense_dns_observer.pfsense_api_configuration_status()
    resolved = PfSenseDNSSettings.from_environment()

    assert status["configured"] is True
    assert status["credential_mode"] == "dedicated_posture"
    assert resolved is not None
    assert resolved.api_key == "posture-read-key"


@pytest.mark.asyncio
async def test_recursive_unbound_is_independent_and_green(monkeypatch, settings) -> None:
    async def fake_get_data(_client, path: str):
        return {
            "/api/v2/system/version": {"version": "2.8.0"},
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
            "/api/v2/system/dns": {"dnsserver": ["172.17.0.24"]},
        }[path]

    monkeypatch.setattr(pfsense_dns_observer, "_get_data", fake_get_data)
    monkeypatch.setattr(
        pfsense_dns_observer,
        "observe_pfsense_ingress_block",
        _security_clear,
    )

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

    filters = {row["id"]: row for row in result["security_filters"]}
    assert filters["firewall"]["state"] == "in_path"
    assert filters["snort"]["state"] == "running"
    assert filters["pfblockerng"]["state"] == "not_observed"
    assert filters["crowdsec"]["state"] == "stopped"
    assert result["ingress_block"]["state"] == "clear"


@pytest.mark.asyncio
async def test_independent_security_evidence_survives_posture_failure(monkeypatch, settings) -> None:
    async def fake_get_data(_client, path: str):
        if path == "/api/v2/system/version":
            request = httpx.Request("GET", "https://pfsense.example.test/api/v2/system/version")
            raise httpx.ConnectTimeout("blocked", request=request)
        return {}

    async def security_blocked():
        return {
            "state": "blocked",
            "engine": "snort",
            "mechanism": "snort2c",
            "control_path": {"mode": "out_of_band", "blind_spot": False},
        }

    monkeypatch.setattr(pfsense_dns_observer, "_get_data", fake_get_data)
    monkeypatch.setattr(
        pfsense_dns_observer,
        "observe_pfsense_ingress_block",
        security_blocked,
    )

    result = await pfsense_dns_observer.observe_pfsense_dns_posture(settings=settings)

    assert result["reachable"] is False
    assert result["ingress_block"]["state"] == "blocked"
    assert result["ingress_block"]["control_path"]["mode"] == "out_of_band"
    filters = {row["id"]: row for row in result["security_filters"]}
    assert filters["firewall"]["state"] == "blocked"
    assert filters["snort"]["state"] == "blocked"


@pytest.mark.asyncio
async def test_posture_deadline_returns_bounded_failure(monkeypatch, settings) -> None:
    async def slow_get_data(_client, _path: str):
        await asyncio.sleep(0.05)
        return {}

    monkeypatch.setattr(pfsense_dns_observer, "_get_data", slow_get_data)
    monkeypatch.setattr(pfsense_dns_observer, "_PFSENSE_POSTURE_DEADLINE_SEC", 0.001)

    result = await pfsense_dns_observer._observe_posture_origin(settings)

    assert result["reachable"] is False
    assert result["error_stage"] == "deadline"
    assert result["error"] == "timeout"


@pytest.mark.asyncio
async def test_snort_filter_survives_services_timeout(monkeypatch, settings) -> None:
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

    result = await pfsense_dns_observer.observe_pfsense_dns_posture(settings=settings)

    assert result["reachable"] is True
    assert result["error_stage"] == "services"
    assert result["error"] == "timeout"
    filters = {row["id"]: row for row in result["security_filters"]}
    assert filters["firewall"]["state"] == "in_path"
    assert filters["snort"]["state"] == "clear"


@pytest.mark.asyncio
async def test_forwarding_only_to_truenas_is_warning(monkeypatch, settings) -> None:
    async def fake_get_data(_client, path: str):
        return {
            "/api/v2/system/version": {"version": "2.8.0"},
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
    monkeypatch.setattr(
        pfsense_dns_observer,
        "observe_pfsense_ingress_block",
        _security_unavailable,
    )

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
            "/api/v2/system/version": {"version": "2.8.0"},
            "/api/v2/status/services": [{"name": "unbound", "status": "stopped"}],
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
        _security_unavailable,
    )

    result = await pfsense_dns_observer.observe_pfsense_dns_posture(settings=settings)

    assert result["policy_state"] == "fail"
    assert result["resolver"]["running"] is False


def test_posture_probe_budget_and_failure_backoff_are_bounded() -> None:
    assert pfsense_dns_observer._PFSENSE_CONNECT_TIMEOUT_SEC == 2.0
    assert pfsense_dns_observer._PFSENSE_READ_TIMEOUT_SEC == 4.0
    assert pfsense_dns_observer._PFSENSE_POSTURE_DEADLINE_SEC == 8.0
    assert pfsense_dns_observer._PFSENSE_MAX_CONCURRENCY == 2
    assert pfsense_dns_observer._PFSENSE_POSTURE_CACHE_POLICY.failure_ttl == 120.0


def test_http_errors_are_redacted() -> None:
    request = httpx.Request("GET", "https://172.17.0.1/api/v2/system/version")
    response = httpx.Response(403, request=request)
    error = httpx.HTTPStatusError("forbidden", request=request, response=response)

    assert pfsense_dns_observer._safe_error(error) == "HTTP 403"
