"""Contracts for pfSense uncertainty in the post-deploy production smoke."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "production-smoke.yml"


def test_pr_smoke_accepts_legacy_transport_only_during_cutover() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert '.checks.pfsense.credential_mode == "disabled"' in text
    assert ".checks.pfsense.authenticated_probes_enabled == false" in text
    assert '.checks.pfsense.observation_mode == "transport_only"' in text
    assert ".checks.pfsense.skipped == true" in text


def test_postdeploy_smoke_requires_authenticated_success_or_cloud_uncertainty() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert '.checks.pfsense.credential_mode == "dedicated_posture"' in text
    assert ".checks.pfsense.api_authenticated == true" in text
    assert ".checks.pfsense.status_confirmed == true" in text
    assert '.checks.pfsense.state == "ok"' in text
    assert ".checks.pfsense.reachable == null" in text
    assert '.checks.pfsense.state == "unknown"' in text
    assert ".checks.pfsense.status_confirmed == false" in text
    assert ".checks.pfsense.degraded == false" in text
    assert '.checks.pfsense.vantage_point == "fastapi_cloud"' in text
    assert 'startswith("⚠️")' in text
    assert '(.checks.pfsense.error_kind | type == "string" and length > 0)' in text
    assert '(.checks.pfsense.failure_stage | type == "string" and length > 0)' in text
