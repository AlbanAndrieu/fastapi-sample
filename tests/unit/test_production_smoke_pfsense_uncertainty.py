"""Contracts for pfSense uncertainty in the post-deploy production smoke."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "production-smoke.yml"


def test_postdeploy_smoke_accepts_only_explicit_cloud_transport_uncertainty() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert '.checks.pfsense.reachable == null' in text
    assert '.checks.pfsense.state == "unknown"' in text
    assert '.checks.pfsense.status_confirmed == false' in text
    assert '.checks.pfsense.degraded == false' in text
    assert '.checks.pfsense.vantage_point == "fastapi_cloud"' in text
    assert 'startswith("⚠️")' in text


def test_postdeploy_smoke_keeps_confirmed_pfsense_failures_distinct() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert '.checks.pfsense.reachable == false' in text
    assert '.checks.pfsense.status_confirmed == true' in text
    assert '(.checks.pfsense.error_kind | type == "string" and length > 0)' in text
    assert '(.checks.pfsense.failure_stage | type == "string" and length > 0)' in text
