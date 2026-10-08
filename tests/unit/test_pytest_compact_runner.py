"""Contracts for concise local pytest output."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "run-pytest-compact.sh"


def test_compact_runner_hides_progress_and_keeps_failure_log() -> None:
    source = RUNNER.read_text(encoding="utf-8")

    assert not source.startswith("#!")
    assert "-p no:sugar" in source
    assert '--tb=short' in source
    assert '>"${LOG}" 2>&1' in source
    assert "full log:" in source
    assert "grep -E" in source
    assert "pytest failed" in source
    assert "date +%Y%m%d-%H%M%S" in source
    assert "$" in source


def test_local_recipes_use_compact_runner() -> None:
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    pytest_ini = (ROOT / "pytest.ini").read_text(encoding="utf-8")

    assert justfile.count("bash scripts/run-pytest-compact.sh") >= 2
    assert "addopts = --random-order" in pytest_ini
    assert "addopts = -v" not in pytest_ini
