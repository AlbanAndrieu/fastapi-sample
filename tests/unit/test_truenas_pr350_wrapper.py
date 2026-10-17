"""Guard the TrueNAS local-first wrapper's executable temporary storage."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts/truenas/run-pr350-tests.sh"


def test_truenas_runner_uses_explicit_python_and_never_downloads() -> None:
    script = WRAPPER.read_text(encoding="utf-8")
    assert 'export UV_PYTHON="/usr/bin/python3.13"' in script
    assert "export UV_PYTHON_DOWNLOADS=never" in script
    assert 'sync --frozen --python "$UV_PYTHON"' in script
    assert "uv run --frozen --no-sync --python" in script
    assert "ERROR: use a detached PR worktree" in script


def test_truenas_runner_protects_exec_required_pytest_fixtures() -> None:
    script = WRAPPER.read_text(encoding="utf-8")
    assert "PR350_TEST_TMPDIR" in script
    assert 'export TMPDIR="$TEST_TMPDIR"' in script
    assert 'mktemp -d "$TMPDIR/pr350-exec.XXXXXX"' in script
    assert '"$exec_probe_dir/probe" >/dev/null 2>&1' in script
    assert 'chmod 700 "$exec_probe_dir/probe"' in script
    assert "pytest -q" in script
    assert "tests/unit/test_agent_publication_proof.py" in script
    assert "bash scripts/agent-quality-gate.sh --fix" in script
