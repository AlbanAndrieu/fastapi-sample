"""Architecture guards for inverse-reachability modules."""

from pathlib import Path


_API_DIR = Path(__file__).parents[2] / "nabla" / "api"


def test_sickz_modules_stay_below_review_threshold() -> None:
    for name in ("sickz_checks.py", "sickz_pfsense.py", "sickz_runtime.py"):
        lines = (_API_DIR / name).read_text(encoding="utf-8").splitlines()
        assert len(lines) < 400, f"{name} regrew to {len(lines)} lines"


def test_sickz_probe_module_delegates_specialized_policy() -> None:
    source = (_API_DIR / "sickz_checks.py").read_text(encoding="utf-8")

    assert "from nabla.api.sickz_pfsense import" in source
    assert "from nabla.api.sickz_runtime import" in source
    assert "def _pfsense_canonical_href" not in source
    assert "def _known_paas_runtime_detected" not in source
