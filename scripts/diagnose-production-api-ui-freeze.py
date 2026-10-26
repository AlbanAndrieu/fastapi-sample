#!/usr/bin/env python3
"""No-secret Chromium /api UI freeze diagnostic, with bounded async operations.

Browser evaluation is time-limited even when JS is consuming the main thread.
Results report *only* selected same-origin HTTP paths and counters.
"""
from __future__ import annotations

import asyncio
import json
import os
from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

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


async def check(target: str) -> dict:
    origin = urlsplit(TARGETS[target]).netloc
    safe_mode = os.getenv("API_UI_SAFE") == "1"
    page_url = TARGETS[target] + ("?ui_safe=1" if safe_mode else "")
    http: list[dict] = []
    failures: list[dict] = []
    page_errors = [0]
    result: dict = {"target": target, "path": "/api", "state": "not_started", "safeMode": safe_mode}
    print(json.dumps({"phase": "launch_chromium", "target": target}), flush=True)
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, timeout=8000)
            try:
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
                print(json.dumps({"phase": "navigate", "target": target}), flush=True)
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

                print(json.dumps({"phase": "observe", "target": target}), flush=True)
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
    except (PlaywrightError, asyncio.TimeoutError):
        result["state"] = "browser_or_transport_unavailable"
        result["next_check"] = "verify_browser_launch_or_network_from_workstation"

    result.update({
        "http": http[-MAX_RECORDS:],
        "requestFailures": failures[-MAX_RECORDS:],
        "pageErrors": page_errors[0],
    })
    return result


def main() -> int:
    target = os.getenv("API_UI_TARGET", "cloud")
    if target not in TARGETS:
        print(json.dumps({"state": "invalid_target", "allowed": sorted(TARGETS)}))
        return 2
    result = asyncio.run(check(target))
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["state"] == "sampled" else 1


if __name__ == "__main__":
    raise SystemExit(main())
