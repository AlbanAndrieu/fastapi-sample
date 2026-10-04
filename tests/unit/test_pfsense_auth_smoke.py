"""Contracts for the deployed pfSense split-identity smoke test."""

from pathlib import Path

from nabla.api import pfsense_auth_smoke


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "nabla" / "api" / "pfsense_auth_smoke.py"


def test_expected_least_privilege_matrix() -> None:
    matrix = {
        (row.identity, row.endpoint): row.expected_status
        for row in pfsense_auth_smoke.EXPECTATIONS
    }

    assert matrix[("posture", "/api/v2/system/version")] == 200
    assert matrix[("posture", "/api/v2/status/services")] == 200
    assert matrix[("posture", "/api/v2/services/dns_resolver/settings")] == 200
    assert matrix[("posture", "/api/v2/system/dns")] == 200
    assert matrix[("posture", "/api/v2/diagnostics/table?id=snort2c")] == 403
    assert matrix[("security", "/api/v2/diagnostics/table?id=snort2c")] == 200
    assert matrix[("security", "/api/v2/status/services")] == 403


def test_smoke_output_contract_is_redacted() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert '"X-API-Key": settings.api_key' in source
    assert "key_present=yes" in source
    assert "secrets_printed=no" in source
    assert "response.text" not in source
    assert "response.json()" not in source
    assert "settings.api_key}" not in source


def test_smoke_rejects_plain_http_before_loading_credentials() -> None:
    assert pfsense_auth_smoke.main(["--url", "http://172.17.0.1:10443"]) == 2
