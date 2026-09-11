"""Least-privilege secret contracts for post-merge reusable workflows."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MASTER_RED = ROOT / ".github/workflows/master-red-remediation.yml"
PYTHON = ROOT / ".github/workflows/python.yml"


def test_master_red_passes_only_named_reusable_workflow_secrets() -> None:
    workflow = MASTER_RED.read_text(encoding="utf-8")

    assert "secrets: inherit" not in workflow
    for mapping in (
        "TRUNK_API_TOKEN: ${{ secrets.TRUNK_API_TOKEN }}",
        "SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}",
        "DOCKER_USERNAME: ${{ secrets.DOCKER_USERNAME }}",
        "DOCKER_PASSWORD: ${{ secrets.DOCKER_PASSWORD }}",
        "CI_PIP_GITLABNABLA_TOKEN: ${{ secrets.CI_PIP_GITLABNABLA_TOKEN }}",
        "CF_ACCESS_CLIENT_ID: ${{ secrets.CF_ACCESS_CLIENT_ID }}",
        "CF_ACCESS_CLIENT_SECRET: ${{ secrets.CF_ACCESS_CLIENT_SECRET }}",
    ):
        assert mapping in workflow

    production_smoke = workflow.split("  production-smoke:", maxsplit=1)[1].split(
        "  codeql:", maxsplit=1,
    )[0]
    assert "secrets:" not in production_smoke


def test_python_reusable_workflow_declares_every_forwarded_secret() -> None:
    workflow = PYTHON.read_text(encoding="utf-8")
    workflow_call = workflow.split("  workflow_call:", maxsplit=1)[1].split(
        "  workflow_dispatch:", maxsplit=1,
    )[0]

    for secret_name in (
        "TRUNK_API_TOKEN",
        "SONAR_TOKEN",
        "DOCKER_USERNAME",
        "DOCKER_PASSWORD",
        "CI_PIP_GITLABNABLA_TOKEN",
    ):
        assert f"      {secret_name}:" in workflow_call
    assert workflow_call.count("required: false") == 5
