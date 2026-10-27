"""Browser and HTTP transport probes remain bounded and privacy-preserving."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_browser_diagnostic_is_async_and_handles_unresponsive_main_thread():
    script = source("scripts/diagnose-production-api-ui-freeze.py")
    compile(script, "scripts/diagnose-production-api-ui-freeze.py", "exec")
    assert "async_playwright()" in script
    assert "service_workers=\"block\"" in script
    assert 'wait_until="commit", timeout=10000' in script
    assert "asyncio.wait_for(page.evaluate(REPORT_JS), timeout=2)" in script
    assert '"main_thread_unresponsive"' in script
    assert "window.__uiFreezeSample" in script
    assert "async def check_browser_preflight()" in script
    assert '"browser_launch_unavailable"' in script
    assert '"browserFailureClass"' in script
    assert '"failedPhase"' in script
    assert '"chromium_binary_missing"' in script
    assert '"chromium_host_dependencies_missing"' in script
    assert '"chromium_sandbox_or_permissions"' in script
    assert '"browser_or_transport_unavailable"' not in script
    assert "longTasks" in script
    assert "page.on(\"pageerror\"" in script
    assert "browser.close()" in script
    for forbidden in (
        "response.text()", "response.body()", "request.headers",
        "cookies()", 'from "playwright"', "X-Diagnostics-Key",
    ):
        assert forbidden not in script


def test_browser_targets_are_pinned_to_cloud_access_and_lan():
    script = source("scripts/diagnose-production-api-ui-freeze.py")
    assert '"cloud": "https://fastapi-sample.fastapicloud.dev/api"' in script
    assert '"staging": "https://sample.albandrieu.com/api"' in script
    assert '"truenas": "http://172.17.0.24:8091/api"' in script
    assert 'if target not in TARGETS:' in script
    assert "urlsplit(response.url).netloc == origin" in script


def test_node_wrapper_streams_phases_and_has_hard_deadline():
    script = source("scripts/diagnose-production-api-ui-freeze.mjs")
    assert 'from "node:child_process"' in script
    assert "spawn(executable, args" in script
    assert 'preflightMode ? (process.env.API_UI_PYTHON || "python3") : "mise"' in script
    assert '"--no-project", "--with", "playwright"' in script
    assert "API_UI_TARGET: target" in script
    assert 'const preflightMode = process.argv.includes("--preflight")' in script
    assert 'API_UI_PREFLIGHT: preflightMode ? "1" : "0"' in script
    assert '"browser_diagnostic_timeout"' in script
    assert "35_000" in script
    assert 'child.kill("SIGKILL")' in script
    assert 'child.stderr.on("data", (part) =>' in script
    assert 'classifyRunnerFailure(privateStderr)' in script
    assert 'runnerFailureClass:' in script
    assert '"from \"playwright\""' not in script


def test_fast_transport_uses_pinned_get_requests_without_body_or_keys():
    script = source("scripts/diagnose-api-ui-transport.py")
    compile(script, "scripts/diagnose-api-ui-transport.py", "exec")
    assert '"/api/ui/session", "/api/ui/services"' in script
    assert 'TIMEOUTS = {"/api": 3, "/api/ui/session": 3, "/api/ui/services": 7}' in script
    assert "timeout=deadline_seconds" in script
    assert '"deadline_seconds": deadline_seconds' in script
    assert 'method="GET"' in script
    assert "NoRedirect" in script
    for forbidden in ("response.read(", "response.text(", "X-Diagnostics-Key", "Authorization", '"Cookie":'):
        assert forbidden not in script



def test_browser_safe_mode_is_explicit_and_allowlisted():
    browser = source("scripts/diagnose-production-api-ui-freeze.py")
    launcher = source("scripts/diagnose-production-api-ui-freeze.mjs")
    ui = source("nabla/api/assets/api-health.js")
    assert 'API_UI_SAFE' in browser
    assert '"?ui_safe=1"' in browser
    assert 'const safeMode = process.argv.includes("--safe")' in launcher
    assert 'API_UI_SAFE: safeMode ? "1" : "0"' in launcher
    assert 'API_UI_FULL: fullMode ? "1" : "0"' in launcher
    assert 'API_UI_PREFLIGHT: preflightMode ? "1" : "0"' in launcher
    assert 'page_url = TARGETS[target] + (' in browser
    assert '"?ui_full=1" if full_mode else ""' in browser
    assert 'get("ui_safe") === "1"' in ui
    assert ui.index('get("ui_safe") === "1"') < ui.index("ownerSessionAvailable()")
    assert 'await installPublicServiceOverview({ ownerAuthenticated: false })' in ui
    assert "installHealthBoardController();" in ui
    assert "return;\n  }\n  const operatorMode =" in ui
    assert "public directory is the resilient default" in ui.lower()
    assert 'params.get("ui_full") === "1"' in ui
    assert 'params.get("operator") === "1"' in ui
