"""Hermetic Playwright startup classification, independent of browser/PyPI."""

import importlib.util
from pathlib import Path
import json
import os
import subprocess
import sys

SRC = Path(__file__).resolve().parents[2] / "scripts/diagnose-api-ui-freeze.py"


def classified(error: str) -> str:
    # The script has no import-time side effects; Playwright is optional there.
    spec = importlib.util.spec_from_file_location("diagnose_api_ui_freeze", SRC)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.classify_chromium_start_failure(RuntimeError(error))


def test_missing_executable_cannot_be_mistaken_for_endpoint_failure():
    assert (
        classified(
            "BrowserType.launch: Executable doesn't exist at /private/browser",
        )
        == "chromium_binary_missing"
    )


def test_missing_libraries_are_explicit():
    assert (
        classified(
            "Host system is missing dependencies to run browsers.",
        )
        == "chromium_host_dependencies_missing"
    )


def test_permission_and_sandbox_failures_are_distinct():
    assert (
        classified(
            "No usable sandbox! -- Chromium denied",
        )
        == "chromium_sandbox_or_permissions"
    )


def test_process_exited_is_not_network_failure():
    assert (
        classified(
            "Target page, context or browser has been closed",
        )
        == "chromium_process_closed"
    )


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


def test_native_offline_preflight_reports_python_playwright_missing_without_network():
    """-S suppresses site packages and reproduces TrueNAS missing dependency."""
    env = {**os.environ, "API_UI_PREFLIGHT": "1", "API_UI_TARGET": "truenas"}
    completed = subprocess.run(
        [sys.executable, "-S", str(SRC)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=6,
    )
    report = json.loads(completed.stdout)
    assert completed.returncode == 2
    assert report == {
        "state": "playwright_python_missing",
        "browser": "not_verified",
        "network_requests_sent": 0,
    }
    assert completed.stderr == ""


def test_no_playwright_ordinary_diagnostic_is_not_mislabeled_ui_freeze():
    env = {**os.environ, "API_UI_PREFLIGHT": "0", "API_UI_TARGET": "truenas"}
    completed = subprocess.run(
        [sys.executable, "-S", str(SRC)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=6,
    )
    report = json.loads(completed.stdout)
    assert completed.returncode == 1
    assert report["state"] == "playwright_python_missing"
    assert report["http"] == []
    assert report["pageErrors"] == 0
    assert completed.stderr == ""
