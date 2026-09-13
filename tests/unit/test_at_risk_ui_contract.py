"""Static contracts for projecting security posture as At risk without downtime."""

from pathlib import Path


ASSETS = Path(__file__).parents[2] / "nabla" / "api" / "assets"


def test_health_board_merges_cloudflare_risk_evidence() -> None:
    dependency = (ASSETS / "api-health-dependency.js").read_text(encoding="utf-8")

    assert '"risk_state"' in dependency
    assert '"risk_reasons"' in dependency
    assert '"exposure"' in dependency
    assert "at risk:" in dependency
    assert "risk unverified:" in dependency


def test_confirmed_security_posture_maps_to_at_risk_not_down() -> None:
    groups = (ASSETS / "api-service-groups.js").read_text(encoding="utf-8")

    assert "function postureAtRisk" in groups
    assert 'risk === "at_risk" || risk === "at-risk"' in groups
    assert 'policy === "warn" || policy === "fail"' in groups
    assert 'if (atRisk) return "At risk";' in groups
    assert 'localState === "fail"' in groups
    assert 'return "Down"' in groups
    assert "rowOutcomeOperational" in groups


def test_main_health_led_uses_amber_for_confirmed_posture_risk() -> None:
    health = (ASSETS / "api-health-core.js").read_text(encoding="utf-8")

    assert "function postureAtRisk" in health
    assert 'dependencyClass === "green" && postureAtRisk(check)' in health
    assert 'if (postureAtRisk(check)) return "yellow";' in health
    assert "check.risk_state" in health
    assert "check.risk_reasons" in health
    assert "check.exposure?.risk_state" in health
    assert "One or more services are at risk" in health
