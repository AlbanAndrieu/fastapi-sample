#!/usr/bin/env python3
"""Read-only Chromium diagnostic for Cloud /api (no credentials or response bodies).

Playwright is provided through the existing optional pytest-playwright/test
extra or `uv run --with playwright`. The Node launcher handles the latter.
"""
from __future__ import annotations

import json
import os
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ALLOWED = {
    "/api", "/api/ui/session", "/api/ui/services", "/api/health-board",
    "/api/site/health/v2", "/api/assets/api-health.js",
    "/api/assets/api-global-service-filter.js",
    "/api/assets/api-health-ui-final-followup.js",
    "/api/assets/api-probe-stable-order.js",
    "/api/assets/api-dom-render-signature.js",
}
DEFAULT = "https://fastapi-sample.fastapicloud.dev/api"
MAX_RECORDS = 45

INIT_JS = r"""
() => {
  window.__uiFreezeSample = { longTasks: 0, longTaskTotalMs: 0, frames: 0 };
  try {
    new PerformanceObserver((entries) => {
      for (const entry of entries.getEntries()) {
        window.__uiFreezeSample.longTasks += 1;
        window.__uiFreezeSample.longTaskTotalMs += entry.duration;
      }
    }).observe({ type: "longtask", buffered: true });
  } catch (_) { /* best effort */ }
  const frame = () => {
    window.__uiFreezeSample.frames += 1;
    window.requestAnimationFrame(frame);
  };
  window.requestAnimationFrame(frame);
}
"""
REPORT_JS = r"""
() => {
  const summary = document.getElementById("health-summary-text");
  const cards = [...document.querySelectorAll("#service-health-overview strong")];
  return {
    summaryLoading: /loading/i.test(summary?.textContent || ""),
    loadingCards: cards.filter(card => /loading/i.test(card.textContent || "")).length,
    publicRows: document.querySelectorAll("#public-services-list .public-service-card").length,
    detailedRows: document.querySelectorAll("#health-checks .health-row").length,
    statusFilterPresent: Boolean(document.getElementById("service-status-filter")),
    longTasks: window.__uiFreezeSample?.longTasks ?? null,
    longTaskTotalMs: Math.round(window.__uiFreezeSample?.longTaskTotalMs ?? 0),
    frames: window.__uiFreezeSample?.frames ?? null
  };
}
"""


def main() -> int:
    target = os.environ.get("PRODUCTION_API_URL", DEFAULT)
    url = urlsplit(target)
    if (url.scheme not in ("https", "http")
            or not url.hostname or url.path != "/api" or url.query or url.fragment
            or url.username or url.password):
        print(json.dumps({"state": "invalid_target"}))
        return 2
    # Do not follow a user-provided external URL outside the known app.
    if url.hostname != "fastapi-sample.fastapicloud.dev":
        print(json.dumps({"state": "unapproved_host"}))
        return 2

    http: list[dict] = []
    failures: list[dict] = []
    errors = [0]
    info: dict = {"state": "not_run"}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(service_workers="block")
                page = context.new_page()
                page.on("response", lambda response: (
                    http.append({"path": urlsplit(response.url).path, "status": response.status})
                    if urlsplit(response.url).netloc == url.netloc
                    and urlsplit(response.url).path in ALLOWED
                    and len(http) < MAX_RECORDS else None
                ))
                page.on("requestfailed", lambda request: (
                    failures.append({"path": urlsplit(request.url).path, "kind": "request_failed"})
                    if urlsplit(request.url).netloc == url.netloc
                    and urlsplit(request.url).path in ALLOWED
                    and len(failures) < MAX_RECORDS else None
                ))
                page.on("pageerror", lambda _error: errors.__setitem__(0, errors[0] + 1))
                page.add_init_script(INIT_JS)
                status = None
                try:
                    navigation = page.goto(target, wait_until="domcontentloaded", timeout=15000)
                    status = navigation.status if navigation is not None else None
                except PlaywrightTimeoutError:
                    info = {"state": "navigation_timeout"}
                except PlaywrightError:
                    info = {"state": "navigation_failed"}
                page.wait_for_timeout(14000)
                try:
                    info = {"state": "sampled", **page.evaluate(REPORT_JS)}
                except PlaywrightError:
                    info = {"state": "main_thread_unresponsive"}
                info["navigationStatus"] = status
            finally:
                browser.close()
    except PlaywrightError:
        info = {"state": "browser_unavailable", "next_check": "uv_run_playwright_install_chromium"}
    print(json.dumps({
        "path": "/api",
        "pageErrors": errors[0],
        "http": http[-MAX_RECORDS:],
        "requestFailures": failures[-MAX_RECORDS:],
        **info,
    }, indent=2, sort_keys=True))
    return 0 if info.get("state") == "sampled" else 1


if __name__ == "__main__":
    raise SystemExit(main())
