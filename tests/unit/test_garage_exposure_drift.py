"""Offline, credential-free exposure reconciliation contract."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit" / "garage_exposure_drift.py"
spec = importlib.util.spec_from_file_location("garage_exposure_drift", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_access_redirect_requires_review_not_origin_bypass():
    declared = {"catalog_revision": "fixture-sha", "services": [
        {"id": "garage-admin", "external": False},
        {"id": "garage-webui", "external": True},
    ]}
    observed = {"observations": [{"service_id": "garage-admin", "layers": {
        "cloudflare_access": {"status": "observed", "http_status": 302,
                               "location": "https://secret.invalid/?token=DO_NOT_COPY"},
    }}]}
    report = module.reconcile(declared, observed)
    admin = report["services"][0]
    assert report["catalog_revision"] == "fixture-sha"
    assert admin["exposure_assessment"] == "requires_review"
    assert admin["origin_anonymously_accessible"] is None
    assert admin["layers"]["public_dns"]["status"] == "unknown"
    assert "DO_NOT_COPY" not in str(report)
    assert report["services"][1]["exposure_assessment"] == "unknown"


def test_confirmed_drift_requires_explicit_evidence():
    result = module.reconcile(
        [{"id": "garage", "external": False}],
        [{"service_id": "garage", "layers": {
            "outside_in_origin": {"status": "drift", "http_status": 200},
        }}],
    )
    assert result["services"][0]["exposure_assessment"] == "confirmed_drift"


@pytest.mark.parametrize("invalid", [
    {"observations": [{"service_id": "garage", "layers": {"public_dns": {"status": "healthy"}}}]},
    {"observations": [{"service_id": "garage"}, {"service_id": "garage"}]},
    {"observations": [{"service_id": "other"}]},
])
def test_rejects_invalid_or_ambiguous_evidence(invalid):
    with pytest.raises(ValueError):
        module.reconcile([{"id": "garage", "external": False}], invalid)
