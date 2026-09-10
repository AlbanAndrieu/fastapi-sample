"""Contracts for post-merge master-red detection and remediation scaffolding."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MASTER_RED = ROOT / ".github/workflows/master-red-remediation.yml"
PYTHON = ROOT / ".github/workflows/python.yml"
PRODUCTION_SMOKE = ROOT / ".github/workflows/production-smoke.yml"
CODEQL = ROOT / ".github/workflows/codeql.yml"
ZAP = ROOT / ".github/workflows/security-zap.yml"


def test_post_merge_gate_covers_quality_runtime_and_security_surfaces() -> None:
    workflow = MASTER_RED.read_text(encoding="utf-8")

    assert "branches: [master]" in workflow
    assert "workflow_dispatch:" in workflow
    assert "uses: ./.github/workflows/python.yml" in workflow
    assert "uses: ./.github/workflows/production-smoke.yml" in workflow
    assert "uses: ./.github/workflows/codeql.yml" in workflow
    assert "uses: ./.github/workflows/security-zap.yml" in workflow
    assert "run_codeql" in workflow
    assert "run_zap" in workflow
    assert "git diff --name-only" in workflow

    for reusable in (PYTHON, PRODUCTION_SMOKE, CODEQL, ZAP):
        assert "workflow_call:" in reusable.read_text(encoding="utf-8")


def test_master_red_remediation_is_deduplicated_and_draft_only() -> None:
    workflow = MASTER_RED.read_text(encoding="utf-8")

    assert 'issue_title="[master-red:${short_sha}] Critical post-merge gates failed"' in workflow
    assert 'branch="remediation/master-red-${short_sha}"' in workflow
    assert 'gh issue list --repo "${REPOSITORY}" --state all' in workflow
    assert 'gh pr list --repo "${REPOSITORY}" --state open --head "${branch}"' in workflow
    assert "--draft" in workflow
    assert "docs/remediation/master-red-${short_sha}.md" in workflow
    assert "MASTER_REMEDIATION_TOKEN || github.token" in workflow
    assert "Do not weaken a failing gate" in workflow


def test_superseded_master_sha_cannot_create_false_remediation_noise() -> None:
    workflow = MASTER_RED.read_text(encoding="utf-8")

    assert "group: master-red-remediation-${{ github.ref }}" in workflow
    assert "cancel-in-progress: true" in workflow
    assert workflow.count("always() && !cancelled()") >= 2
    assert "Keep red master visible until remediation" in workflow
