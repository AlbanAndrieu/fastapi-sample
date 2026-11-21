"""Contracts for post-merge master-red detection and remediation scaffolding."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MASTER_RED = ROOT / ".github/workflows/master-red-remediation.yml"
PYTHON = ROOT / ".github/workflows/python.yml"
PRODUCTION_SMOKE = ROOT / ".github/workflows/master-smoke.yml"
CODEQL = ROOT / ".github/workflows/codeql.yml"
ZAP = ROOT / ".github/workflows/security-zap.yml"


def test_post_merge_gate_covers_quality_runtime_and_security_surfaces() -> None:
    workflow = MASTER_RED.read_text(encoding="utf-8")

    assert "branches: [master]" in workflow
    assert "workflow_dispatch:" in workflow
    assert "uses: $/.github/workflows/python.yml" in workflow
    assert "uses: $/.github/workflows/master-smoke.yml" in workflow
    assert "uses: $/.github/workflows/codeql.yml" in workflow
    assert "uses: $/.github/workflows/security-zap.yml" in workflow
    assert "run_codeql" in workflow
    assert "run_zap" in workflow
    assert "git diff --name-only" in workflow

    for reusable in (PYTHON, PRODUCTION_SMOKE, CODEQL, ZAP):
        assert "workflow_call:" in reusable.read_text(encoding="utf-8")


def test_master_red_reuses_one_issue_and_never_creates_draft_noise() -> None:
    workflow = MASTER_RED.read_text(encoding="utf-8")
    assert "name: Track latest master in one manual-safe status comment" in workflow
    assert "scripts/ci/master_red_issue.py --apply" in workflow
    assert "issues: write" in workflow
    assert "GH_TOKEN: ${{ github.token }}" in workflow
    assert "if: ${{ always() && !cancelled() }}" in workflow
    assert "GITHUB_RUN_NUMBER" not in workflow  # supplied by Actions runtime
    for forbidden in (
        "gh issue create",
        "gh pr create",
        "gh issue edit",
        "MASTER_REMEDIATION_TOKEN",
        "remediation/master-red-",
    ):
        assert forbidden not in workflow


def test_superseded_master_sha_cannot_create_false_remediation_noise() -> None:
    workflow = MASTER_RED.read_text(encoding="utf-8")

    assert "group: master-red-remediation-${{ github.ref }}" in workflow
    assert "cancel-in-progress: true" in workflow
    assert workflow.count("always() && !cancelled()") >= 2
    assert "Keep red master visible until remediation" in workflow
