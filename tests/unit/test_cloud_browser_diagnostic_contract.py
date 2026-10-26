"""Cloud browser incident diagnostic remains read-only and reproducible."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_browser_diagnostic_python_compiles_and_redacts_evidence():
    source = (ROOT / "scripts/diagnose-production-api-ui-freeze.py").read_text()
    compile(source, "scripts/diagnose-production-api-ui-freeze.py", "exec")
    assert "sync_playwright()" in source
    assert "service_workers=\"block\"" in source
    assert "browserMainThread" not in source
    assert "window.__uiFreezeSample" in source
    assert "longTasks" in source
    assert "path" in source and "status" in source
    assert "password" in source
    assert "response.text()" not in source
    assert "response.body()" not in source
    assert "request.headers" not in source
    assert "cookies()" not in source
    assert "goto(target, wait_until=\"domcontentloaded\", timeout=15000)" in source


def test_node_wrapper_runs_python_in_isolated_uv_no_project_mode():
    source = (ROOT / "scripts/diagnose-production-api-ui-freeze.mjs").read_text()
    assert '"--no-project", "--with", "playwright"' in source
    assert "diagnose-production-api-ui-freeze.py" in source
    assert '"mise"' in source
    assert '"inherit"' in source
    assert "timeout: 50_000" in source
    assert 'from "playwright"' not in source
    assert 'import("playwright")' not in source
    assert "node_modules" in source
