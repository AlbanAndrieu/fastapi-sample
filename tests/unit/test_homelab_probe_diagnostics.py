"""Diagnostic labels must not claim origin downtime from Access edge evidence."""

import pytest

from nabla.api.homelab_probe_diagnostics import classify_probe_diagnostic


@pytest.mark.parametrize(
    ("row", "category"),
    [
        ({"state": "warn", "cloudflare_default_deny": True, "http_status": 403}, "ACCESS_PROTECTED"),
        ({"state": "warn", "cloudflare_service_token_rejected": True}, "AUTH_FAILED"),
        ({"state": "warn", "public_probe_verification": "origin_unverified"}, "ORIGIN_UNVERIFIED"),
        ({"state": "fail", "error_kind": "NameResolutionError"}, "DNS"),
        ({"state": "fail", "error_kind": "dns_lookup"}, "DNS"),
        ({"state": "fail", "error_kind": "ssl_certificate"}, "TLS"),
        ({"state": "fail", "error_kind": "ConnectTimeout"}, "TIMEOUT"),
        ({"state": "fail", "origin_reached": True, "http_status": 503}, "ORIGIN_ERROR"),
        ({"state": "warn", "http_status": 401}, "AUTH_REQUIRED"),
        ({"state": "warn", "probe_stale": True}, "STALE"),
        ({"state": "ok", "http_status": 200}, None),
    ],
)
def test_diagnostic_evidence_categories(row: dict, category: str | None) -> None:
    assert classify_probe_diagnostic(row) == category


def test_cloudflare_access_never_becomes_confirmed_origin_down() -> None:
    row = {
        "state": "warn",
        "origin_reached": False,
        "http_status": 502,
        "public_probe_verification": "access_protected_origin_unverified",
    }
    assert classify_probe_diagnostic(row) == "ACCESS_PROTECTED"
