"""Regression tests for post-deployment diagnostic smoke semantics."""

import re
from pathlib import Path

import yaml

from nabla.access_control import _SMOKE_READ_ROUTES

ROOT = Path(__file__).resolve().parents[2]


def test_production_smoke_accepts_classified_transient_pfsense_failures() -> None:
    smoke = (ROOT / ".github/workflows/master-smoke.yml").read_text(encoding="utf-8")

    assert "Check production runtime topology" in smoke
    assert '"${PRODUCTION_API_URL}/runtime/topology"' in smoke
    assert ".platform_replica_count_available == false" in smoke
    assert '.checks.pfsense.credential_mode == "disabled"' in smoke
    assert ".checks.pfsense.authenticated_probes_enabled == false" in smoke
    assert '.checks.pfsense.observation_mode == "transport_only"' in smoke
    assert ".checks.pfsense.skipped == true" in smoke
    assert '.checks.pfsense.credential_mode == "dedicated_posture"' in smoke
    assert '.checks.pfsense.error_kind | type == "string"' in smoke
    assert '.checks.pfsense.failure_stage | type == "string"' in smoke
    assert ".checks.pfsense.api_authenticated == true" in smoke
    assert ".checks.pfsense.status_confirmed == true" in smoke
    assert '.checks.pfsense.state == "ok"' in smoke
    assert ".checks.pfsense.reachable == null" in smoke
    assert '.checks.pfsense.state == "unknown"' in smoke
    assert ".checks.pfsense.status_confirmed == false" in smoke
    assert ".checks.pfsense.degraded == false" in smoke
    assert '.checks.pfsense.vantage_point == "fastapi_cloud"' in smoke
    assert '"telemetry_stale"' in smoke
    assert '"telemetry_unavailable"' in smoke
    assert ".pfsense.dns.ingress_block.last_success_at" in smoke
    assert ".pfsense.dns.ingress_block.attribution_available == false" in smoke
    assert '.pfsense.dns.ingress_block.state != "telemetry_unavailable"' not in smoke


def test_smoke_key_stays_in_the_post_deploy_job_and_never_prints_payloads() -> None:
    """Public repo logs: the dedicated key reads, asserts and prints nothing private."""
    text = (ROOT / ".github/workflows/master-smoke.yml").read_text(encoding="utf-8")
    jobs = yaml.safe_load(text)["jobs"]
    public, private = jobs["production-smoke"], jobs["authenticated-smoke"]

    assert "environment" not in public
    assert "secrets." not in yaml.safe_dump(public)
    assert private["environment"] == "production-smoke"
    assert private["if"] == "${{ github.event_name != 'pull_request' }}"
    assert text.count("secrets.PRODUCTION_SMOKE_ACCESS_KEY") == 2
    assert "X-Diagnostics-Key" not in text and "Authorization" not in text
    assert "| jq ." not in text and "::group::" not in text

    # The anonymous 401 probe and the code allowlist cover exactly the same routes.
    probe = next(step["run"] for step in public["steps"] if step["name"] == "Verify private diagnostics refuse anonymous reads")
    probed = {("/api" if base == "API" else "") + path for base, path in re.findall(r'"\$\{PRODUCTION_(ROOT|API)_URL\}(/[^"]+)"', probe)}
    assert probed == set(_SMOKE_READ_ROUTES)
