"""Architecture guards for the split deep-health modules."""

from pathlib import Path


_API_DIR = Path(__file__).parents[2] / "nabla" / "api"


def test_deep_health_modules_stay_below_review_threshold() -> None:
    for name in ("health_checks.py", "integration_health.py"):
        lines = (_API_DIR / name).read_text(encoding="utf-8").splitlines()
        assert len(lines) < 400, f"{name} regrew to {len(lines)} lines"


def test_health_orchestrator_delegates_optional_integrations() -> None:
    source = (_API_DIR / "health_checks.py").read_text(encoding="utf-8")

    assert "from nabla.api.integration_health import" in source
    assert "def probe_brave_search" not in source
    assert "def probe_litellm_public_proxy" not in source
    assert "def probe_pyroscope_server" not in source
