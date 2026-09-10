"""Security contracts for the dual Web/OpenAPI ZAP workflow."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/security-zap.yml"


def test_zap_scans_web_and_openapi_on_ephemeral_local_runtime() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "OWASP ZAP Web baseline" in workflow
    assert "OWASP ZAP OpenAPI active scan" in workflow
    assert "zaproxy/action-baseline@de8ad967d3548d44ef623df22cf95c3b0baf8b25" in workflow
    assert "zaproxy/action-api-scan@5158fe4d9d8fcc75ea204db81317cce7f9e5453d" in workflow
    assert "${{ env.BASE_URL }}/api" in workflow
    assert "${{ env.BASE_URL }}/openapi.json" in workflow
    assert "format: openapi" in workflow
    assert "127.0.0.1:8080" in workflow
    assert "--lifespan off" in workflow
    assert 'curl --fail --silent --show-error "$BASE_URL/api"' in workflow
    assert 'curl --fail --silent --show-error "$BASE_URL/openapi.json"' in workflow
    assert "uv sync --frozen --no-default-groups" in workflow
    assert "workflow_call:" in workflow
    assert "fastapi-sample.fastapicloud.dev/openapi.json" not in workflow
    assert "home.albandrieu.com:10443" not in workflow


def test_zap_policy_distinguishes_web_and_api_findings() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert ".zap/web-rules.tsv" in workflow
    assert ".zap/api-rules.tsv" in workflow
    assert "zap-web-report" in workflow
    assert "zap-api-report" in workflow
    assert "WEB_OUTCOME" in workflow and "API_OUTCOME" in workflow
    assert "no production/TrueNAS/pfSense target is attacked" in workflow
