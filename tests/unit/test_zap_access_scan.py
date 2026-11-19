"""Authentication and report-redaction contracts (no network or Docker)."""

import importlib.util
from pathlib import Path
import re

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/security/zap_access_scan.py"
SPEC = importlib.util.spec_from_file_location("zap_access_scan", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_auth_headers_are_exact_host_only() -> None:
    config = MODULE.auth_properties(("fake-id", "fake-secret"))
    assert config.count(".url=" + MODULE.HOST_PATTERN) == 2
    assert re.fullmatch(MODULE.HOST_PATTERN, "https://fastapi-sample.albandrieu.com/api")
    assert not re.fullmatch(MODULE.HOST_PATTERN, "https://fastapi-sample.albandrieu.com.evil.test/api")
    assert not re.fullmatch(MODULE.HOST_PATTERN, "https://evil.test/fastapi-sample.albandrieu.com/api")
    assert not re.fullmatch(MODULE.HOST_PATTERN, "http://fastapi-sample.albandrieu.com/api")


def test_report_drops_sensitive_requests_and_responses() -> None:
    payload = {"site": [{"@name": MODULE.ORIGIN, "alerts": [{
        "pluginid": "10021", "riskcode": "1", "confidence": "2", "count": "1",
        "name": "secret", "instances": [{"uri": "https://example.test/?token=secret", "evidence": "secret"}],
    }]}]}
    assert MODULE.alert_summary(payload) == [{"pluginId": 10021, "risk": 1, "confidence": 2, "instances": 1}]


def test_invalid_report_cannot_be_treated_as_clean() -> None:
    with pytest.raises(KeyError):
        MODULE.alert_summary({"invalid": []})


def test_empty_or_unrelated_site_cannot_be_reported_as_clean() -> None:
    for payload in ({"site": []}, {"site": [{"@name": "https://foreign.test", "alerts": []}]}):
        with pytest.raises(ValueError, match="expected target origin"):
            MODULE.alert_summary(payload)
