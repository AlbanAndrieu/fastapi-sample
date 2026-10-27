#!/usr/bin/env python3
"""No-secret Chromium /api UI freeze diagnostic, with bounded async operations.

Browser evaluation is time-limited even when JS is consuming the main thread.
Results report *only* selected same-origin HTTP paths and counters.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

# The offline preflight must work even on a TrueNAS host without Playwright.
# Never install packages or download Chromium as part of diagnosis.
try:
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

    class PlaywrightError(Exception):
        """Placeholder only when the optional browser dependency is absent."""

    class PlaywrightTimeoutError(PlaywrightError):
        """Placeholder to preserve explicit failure handling in offline mode."""

TARGETS = {
    "cloud": "https://fastapi-sample.fastapicloud.dev/api",
    "staging": "https://sample.albandrieu.com/api",
    "truenas": "http://172.17.0.24:8091/api",
}
ALLOWED = {
    "/api", "/api/ui/session", "/api/ui/services", "/api/health-board",
    "/api/site/health/v2", "/api/assets/api-health.js",
    "/api/assets/api-global-service-filter.js",
    "/api/assets/api-health-ui-final-followup.js",
    "/api/assets/api-probe-stable-order.js",
    "/api/assets/api-dom-render-signature.js",
}
MAX_RECORDS = 45
INIT_JS = r"""
(() => {
  window.__uiFreezeSample = { longTasks: 0, longTaskTotalMs: 0, frames: 0 };
  try {
    new PerformanceObserver((entries) => {
      for (const entry of entries.getEntries()) {
        window.__uiFreezeSample.longTasks += 1;
        window.__uiFreezeSample.longTaskTotalMs += entry.duration;
      }
    }).observe({ type: "longtask", buffered: true });
  } catch (_) {}
  const frame = () => {
    window.__uiFreezeSample.frames += 1;
    window.requestAnimationFrame(frame);
  };
  window.requestAnimationFrame(frame);
})();
"""
REPORT_JS = r"""
() => {
  const summary = document.getElementById("health-summary-text");
  return {
    summaryLoading: /loading/i.test(summary?.textContent || ""),
    publicRows: document.querySelectorAll("#public-services-list .public-service-card").length,
    detailedRows: document.querySelectorAll("#health-checks .health-row").length,
    statusFilterPresent: Boolean(document.getElementById("service-status-filter")),
    longTasks: window.__uiFreezeSample?.longTasks ?? null,
    longTaskTotalMs: Math.round(window.__uiFreezeSample?.longTaskTotalMs ?? 0),
    frames: window.__uiFreezeSample?.frames ?? null
  };
}
"""


def classify_chromium_start_failure(exc: BaseException) -> str:
    """Emit a fixed label, never Playwright stderr or executable paths."""
    message = str(exc).lower()
    if "executable doesn't exist" in message or "browser was not found" in message:
        return "chromium_binary_missing"
    if "host system is missing dependencies" in message or "error while loading shared libraries" in message:
        return "chromium_host_dependencies_missing"
    if "no usable sandbox" in message or "operation not permitted" in message or "permission denied" in message:
        return "chromium_sandbox_or_permissions"
    if "target page, context or browser has been closed" in message:
        return "chromium_process_closed"
    return "chromium_start_unknown"


async def check_browser_preflight() -> dict:
    """Check Playwright's pinned Chromium path without launching or networking."""
    if async_playwright is None:
        return {
            "state": "playwright_python_missing",
            "browser": "not_verified",
            "network_requests_sent": 0,
        }
    try:
        async with async_playwright() as playwright:
            chromium = Path(playwright.chromium.executable_path)
            available = chromium.is_file()
            executable = available and os.access(chromium, os.X_OK)
    except (PlaywrightError, OSError, asyncio.TimeoutError):
        return {"state": "playwright_driver_unavailable", "browser": "not_verified"}
    return {
        "state": "browser_binary_ready" if executable else "chromium_binary_missing",
        "browser": "present_executable" if executable else "missing_or_not_executable",
        "network_requests_sent": 0,
    }


async def check(target: str) -> dict:
    origin = urlsplit(TARGETS[target]).netloc
    safe_mode = os.getenv("API_UI_SAFE") == "1"
    full_mode = os.getenv("API_UI_FULL") == "1"
    page_url = TARGETS[target] + (
        "?ui_safe=1" if safe_mode else "?ui_full=1" if full_mode else ""
    )
    http: list[dict] = []
    failures: list[dict] = []
    page_errors = [0]
    result: dict = {"target": target, "path": "/api", "state": "not_started", "safeMode": safe_mode, "fullMode": full_mode}
    if async_playwright is None:
        return {
            **result,
            "state": "playwright_python_missing",
            "next_check": "install_playwright_in_selected_python_environment",
            "http": [],
            "requestFailures": [],
            "pageErrors": 0,
        }
    phase = "launch_chromium"
    print(json.dumps({"phase": phase, "target": target}), flush=True)
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, timeout=8000)
            try:
                phase = "create_browser_context"
                context = await browser.new_context(service_workers="block")
                page = await context.new_page()
                page.on("response", lambda response: (
                    http.append({"path": urlsplit(response.url).path, "status": response.status})
                    if urlsplit(response.url).netloc == origin
                    and urlsplit(response.url).path in ALLOWED
                    and len(http) < MAX_RECORDS else None
                ))
                page.on("requestfailed", lambda request: (
                    failures.append({"path": urlsplit(request.url).path, "kind": "request_failed"})
                    if urlsplit(request.url).netloc == origin
                    and urlsplit(request.url).path in ALLOWED
                    and len(failures) < MAX_RECORDS else None
                ))
                page.on("pageerror", lambda _error: page_errors.__setitem__(0, page_errors[0] + 1))
                await page.add_init_script(INIT_JS)

                status = None
                navigation_state = "not_started"
                phase = "navigate"
                print(json.dumps({"phase": phase, "target": target}), flush=True)
                try:
                    response = await page.goto(
                        page_url, wait_until="commit", timeout=10000,
                    )
                    status = response.status if response is not None else None
                    navigation_state = "committed"
                except PlaywrightTimeoutError:
                    navigation_state = "timeout"
                except PlaywrightError:
                    navigation_state = "failed"
                try:
                    redirected = urlsplit(page.url).netloc not in ("", origin)
                except (ValueError, TypeError):
                    redirected = False

                # Never claim an empty/about:blank page was sampled after a
                # failed navigation. Access redirects are not JS freezes.
                if navigation_state != "committed":
                    result["state"] = (
                        "navigation_timeout" if navigation_state == "timeout"
                        else "navigation_failed"
                    )
                    result["next_check"] = "verify_pinned_http_transport"
                elif redirected:
                    result["state"] = "redirected_off_origin"
                    result["next_check"] = "verify_external_access_policy"
                elif status in (401, 403):
                    result["state"] = "http_access_restricted"
                    result["next_check"] = "verify_expected_authentication_policy"
                else:
                    phase = "observe"
                    print(json.dumps({"phase": phase, "target": target}), flush=True)
                    await asyncio.sleep(8)
                    try:
                        sample = await asyncio.wait_for(page.evaluate(REPORT_JS), timeout=2)
                        result["state"] = "sampled"
                        result.update(sample)
                    except (asyncio.TimeoutError, PlaywrightTimeoutError):
                        result["state"] = "main_thread_unresponsive"
                    except PlaywrightError:
                        result["state"] = "browser_page_unavailable"
                result.update({
                    "navigationStatus": status,
                    "navigationState": navigation_state,
                    "redirectedOffOrigin": redirected,
                })
            finally:
                # Never hide the observed failure waiting for an unresponsive
                # page/browser to close; the JS launcher has a hard kill limit.
                try:
                    await asyncio.wait_for(browser.close(), timeout=2)
                except (asyncio.TimeoutError, PlaywrightError):
                    pass
    except (PlaywrightError, asyncio.TimeoutError) as exc:
        result["failedPhase"] = phase
        if phase == "launch_chromium":
            result["state"] = "browser_launch_unavailable"
            result["browserFailureClass"] = classify_chromium_start_failure(exc)
            result["next_check"] = "verify_local_chromium_binary_and_host_dependencies"
        elif phase == "create_browser_context":
            result["state"] = "browser_context_unavailable"
            result["next_check"] = "verify_browser_context_initialization"
        else:
            result["state"] = "browser_session_unavailable"
            result["next_check"] = "verify_browser_page_without_disclosing_runtime_errors"

    result.update({
        "http": http[-MAX_RECORDS:],
        "requestFailures": failures[-MAX_RECORDS:],
        "pageErrors": page_errors[0],
    })
    return result


def main() -> int:
    if os.getenv("API_UI_PREFLIGHT") == "1":
        report = asyncio.run(check_browser_preflight())
        print(json.dumps(report, sort_keys=True), flush=True)
        return 0 if report["state"] == "browser_binary_ready" else 2
    target = os.getenv("API_UI_TARGET", "cloud")
    if target not in TARGETS:
        print(json.dumps({"state": "invalid_target", "allowed": sorted(TARGETS)}))
        return 2
    result = asyncio.run(check(target))
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["state"] == "sampled" else 1


if __name__ == "__main__":
    raise SystemExit(main())
