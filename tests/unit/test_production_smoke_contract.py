"""Regression tests for post-deployment diagnostic smoke semantics."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_production_smoke_accepts_classified_transient_pfsense_failures() -> None:
    smoke = (ROOT / ".github/workflows/production-smoke.yml").read_text(encoding="utf-8")

    assert "Check production runtime topology" in smoke
    assert '"${PRODUCTION_API_URL}/runtime/topology"' in smoke
    assert ".platform_replica_count_available == false" in smoke
    assert '.checks.pfsense.credential_mode == "dedicated_posture"' in smoke
    assert '.checks.pfsense.error_kind | type == "string"' in smoke
    assert '.checks.pfsense.failure_stage | type == "string"' in smoke
    assert '"telemetry_stale"' in smoke
    assert '"telemetry_unavailable"' in smoke
    assert '.pfsense.dns.ingress_block.last_success_at' in smoke
    assert '.pfsense.dns.ingress_block.attribution_available == false' in smoke
    assert '.pfsense.dns.ingress_block.state != "telemetry_unavailable"' not in smoke
