"""Cost-aware security scan and DefectDojo import contracts."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _flat(code: str) -> str:
    """Collapse whitespace so formatter line wrapping does not break contracts."""
    return " ".join(code.split())


def _call_keywords(code: str, name: str) -> set[str]:
    return {
        keyword.arg for node in ast.walk(ast.parse(code)) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name for keyword in node.keywords
    }


def test_security_scan_requires_real_tools_and_no_pr_dast() -> None:
    code = (ROOT / "scripts/security/run_security_scans.py").read_text()
    flat = _flat(code)
    assert 'if args.dast and args.mode != "master":' in code
    assert '"uv.lock"' not in code.split("def _trivy(")[1].split("def _betterleaks(")[0]
    assert '"package-lock.json"' not in code.split("def _trivy(")[1].split("def _betterleaks(")[0]
    assert '"--dast"' in code
    assert '"fastapi-sample"' in code
    assert '"nabla-site-alban"' not in code
    assert "scan-receipt.json" in code
    assert {"mode", "dast"} <= _call_keywords(code, "_write_completed_receipt")
    assert '"--scanners", "vuln,misconfig,secret,license"' in flat
    assert '"cyclonedx"' in code
    assert '"--license-full"' in code
    assert '"--redact=100"' in code
    assert code.index("os.umask(0o077)") < code.index("tempfile.mkdtemp(")
    ast.parse(code)


def test_importer_does_not_allow_secret_or_sarif_uploads() -> None:
    code = (ROOT / "scripts/security/import_defectdojo.py").read_text()
    assert '"betterleaks"' not in code
    assert '"sarif"' not in code
    # Raw http.client never follows redirects; urllib redirect handlers are banned.
    assert "http.client.HTTPSConnection" in code
    assert "urllib" not in code
    assert "Trivy secret evidence is forbidden for import" in code
    assert "report directory must be private" in code
    assert "def approved_report" in code
    assert '"/api/v2/reimport-scan/"' in code
    ast.parse(code)


def test_pr_security_checks_have_enforced_secret_scanners() -> None:
    precommit = (ROOT / ".pre-commit-config.yaml").read_text()
    megalinter = (ROOT / ".mega-linter.yml").read_text()
    codeql = (ROOT / ".github/workflows/codeql.yml").read_text()
    assert "- id: betterleaks" in precommit
    assert "REPOSITORY_BETTERLEAKS_DISABLE_ERRORS: false" in megalinter
    assert "REPOSITORY_TRIVY_DISABLE_ERRORS: false" in megalinter
    assert "pull_request:" in codeql
