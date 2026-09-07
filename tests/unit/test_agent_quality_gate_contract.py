"""Contract tests for the agent-first pre-build quality gate."""

from __future__ import annotations

import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_agent_quality_gate_wraps_tests_and_canonical_gate() -> None:
    gate = ROOT / "scripts" / "agent-quality-gate.sh"
    mode = stat.S_IMODE(gate.stat().st_mode)
    text = gate.read_text(encoding="utf-8")

    assert mode & stat.S_IXUSR
    assert "QG_BASE_STALE" in text
    assert "QG_LARGE_DELETION" in text
    assert "QG_EXEC_BIT" in text
    assert "uv run pytest -q --disable-warnings --maxfail=1" in text
    assert "uv run python scripts/check_versions.py" in text
    assert "bash scripts/quality-gate.sh" in text
    assert 'tail -n "${LOG_TAIL}"' in text


def test_pre_push_uses_agent_quality_gate() -> None:
    config = (ROOT / ".pre-commit-pre-push.yaml").read_text(encoding="utf-8")

    assert "entry: bash scripts/agent-quality-gate.sh" in config


def test_python_ci_gates_builds_behind_preflight() -> None:
    workflow = (ROOT / ".github/workflows/python.yml").read_text(encoding="utf-8")

    assert "\n  preflight:\n" in workflow
    assert "run: bash scripts/agent-quality-gate.sh" in workflow
    assert "QUALITY_BASE_REF: origin/${{ github.base_ref }}" in workflow
    assert "\n    needs: preflight\n" in workflow
    assert "github.event.pull_request.draft == false" in workflow
    assert "uv run pytest --junit-xml=junit.xml" not in workflow


def test_production_smoke_does_not_run_on_every_pr_synchronize() -> None:
    workflow = (ROOT / ".github/workflows/production-smoke.yml").read_text(
        encoding="utf-8"
    )

    assert "types: [opened, ready_for_review]" in workflow
    assert "synchronize" not in workflow.split("jobs:", maxsplit=1)[0]
    assert "github.event.pull_request.draft == false" in workflow
