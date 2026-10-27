"""Hermetic Playwright startup classification, independent of browser/PyPI."""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "scripts/diagnose-production-api-ui-freeze.py"


def classified(error: str) -> str:
    tree = ast.parse(SRC.read_text(encoding="utf8"))
    nodes = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "classify_chromium_start_failure"
    ]
    assert len(nodes) == 1
    isolated = ast.Module(body=nodes, type_ignores=[])
    namespace = {"BaseException": BaseException}
    exec(compile(isolated, str(SRC), "exec"), namespace)
    return namespace["classify_chromium_start_failure"](RuntimeError(error))


def test_missing_executable_cannot_be_mistaken_for_endpoint_failure():
    assert classified(
        "BrowserType.launch: Executable doesn't exist at /private/browser"
    ) == "chromium_binary_missing"


def test_missing_libraries_are_explicit():
    assert classified(
        "Host system is missing dependencies to run browsers."
    ) == "chromium_host_dependencies_missing"


def test_permission_and_sandbox_failures_are_distinct():
    assert classified(
        "No usable sandbox! -- Chromium denied"
    ) == "chromium_sandbox_or_permissions"


def test_process_exited_is_not_network_failure():
    assert classified(
        "Target page, context or browser has been closed"
    ) == "chromium_process_closed"


def test_unknown_private_playwright_message_is_never_emitted():
    marker = "PRIVATE_API_TOKEN=value_do_not_echo"
    assert classified(marker) == "chromium_start_unknown"
    assert marker not in classified(marker)


def test_browser_diagnostic_has_no_install_or_network_preflight():
    script = SRC.read_text(encoding="utf8")
    assert "chromium.executable_path" in script
    assert "chromium.is_file()" in script
    assert "os.access(chromium, os.X_OK)" in script
    assert '"network_requests_sent": 0' in script
    assert "playwright install chromium" not in script
    assert "browser_or_transport_unavailable" not in script
