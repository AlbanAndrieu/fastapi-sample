"""Security contracts for the post-deployment Web/OpenAPI ZAP workflow."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/security-zap.yml"


def test_zap_scans_authorized_production_web_and_openapi_surfaces() -> None:
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    triggers = workflow_text.split("jobs:", maxsplit=1)[0]
    dast_env = workflow["jobs"]["dast"]["env"]

    assert "pull_request:" not in triggers
    assert "workflow_call:" in triggers
    assert "workflow_dispatch:" in triggers
    assert "127.0.0.1" not in workflow_text
    assert "uvicorn" not in workflow_text
    assert "--lifespan off" not in workflow_text

    assert "zaproxy/action-baseline@de8ad967d3548d44ef623df22cf95c3b0baf8b25" in workflow_text
    assert "zaproxy/action-api-scan@5158fe4d9d8fcc75ea204db81317cce7f9e5453d" in workflow_text
    assert dast_env["TRUENAS_ROOT_URL"] == "https://sample.albandrieu.com/"
    assert dast_env["TRUENAS_API_URL"] == "https://sample.albandrieu.com/api"
    assert dast_env["TRUENAS_OPENAPI_URL"] == "https://sample.albandrieu.com/openapi.json"
    assert dast_env["CLOUD_API_URL"] == "https://fastapi-sample.fastapicloud.dev/api"
    assert dast_env["CLOUD_OPENAPI_URL"] == "https://fastapi-sample.fastapicloud.dev/openapi.json"
    assert workflow_text.count("format: openapi") == 2


def test_zap_policy_keeps_auth_findings_and_management_boundaries_explicit() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert ".zap/web-rules.tsv" in workflow
    assert ".zap/api-rules.tsv" in workflow
    assert "CF-Access-Client-Id" in workflow
    assert "CF-Access-Client-Secret" in workflow
    assert "Management APIs for pfSense and TrueNAS are intentionally excluded" in workflow
    assert "home.albandrieu.com:10443" not in workflow
    assert workflow.count("fail_action: true") == 5
    assert "-I -T 4 -s" in workflow
    assert "timeout-minutes: 30" in workflow

    for artifact in (
        "zap-web-truenas-root",
        "zap-web-truenas-api",
        "zap-web-fastapi-cloud-api",
        "zap-api-truenas",
        "zap-api-fastapi-cloud",
    ):
        assert artifact in workflow

    for outcome in (
        "TRUENAS_ROOT_OUTCOME",
        "TRUENAS_API_OUTCOME",
        "CLOUD_WEB_OUTCOME",
        "TRUENAS_OPENAPI_OUTCOME",
        "CLOUD_OPENAPI_OUTCOME",
    ):
        assert outcome in workflow

    assert "At least one production ZAP Web/OpenAPI scan did not satisfy the blocking policy" in workflow
