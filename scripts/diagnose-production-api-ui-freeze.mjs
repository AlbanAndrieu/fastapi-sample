// Read-only production browser diagnosis. Never read response bodies,
// cookies, diagnostics keys or URLs outside the known same-origin paths.
import { chromium } from "playwright";

const target = new URL(
  process.env.PRODUCTION_API_URL || "https://fastapi-sample.fastapicloud.dev/api",
);
if (!["https:", "http:"].includes(target.protocol) || target.pathname !== "/api") {
  throw new Error("PRODUCTION_API_URL must be an /api page");
}
const observedPaths = new Set([
  "/api", "/api/ui/session", "/api/ui/services",
  "/api/health-board", "/api/assets/api-health.js",
  "/api/assets/api-global-service-filter.js",
  "/api/assets/api-health-ui-final-followup.js",
  "/api/assets/api-probe-stable-order.js",
  "/api/assets/api-dom-render-signature.js",
]);
const http = [];
const failed = [];
let pageErrors = 0;
const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext({ serviceWorkers: "block" });
  const page = await context.newPage();
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (url.origin === target.origin && observedPaths.has(url.pathname)) {
      http.push({ path: url.pathname, status: response.status() });
    }
  });
  page.on("requestfailed", (request) => {
    const url = new URL(request.url());
    if (url.origin === target.origin && observedPaths.has(url.pathname)) {
      failed.push({ path: url.pathname, kind: "request_failed" });
    }
  });
  page.on("pageerror", () => { pageErrors += 1; });
  await page.addInitScript(() => {
    window.__uiFreezeSample = { longTasks: 0, longTaskTotalMs: 0, frames: 0 };
    try {
      new PerformanceObserver((entries) => {
        for (const entry of entries.getEntries()) {
          window.__uiFreezeSample.longTasks += 1;
          window.__uiFreezeSample.longTaskTotalMs += entry.duration;
        }
      }).observe({ type: "longtask", buffered: true });
    } catch {
      // Some browsers do not expose Long Tasks.
    }
    const frame = () => {
      window.__uiFreezeSample.frames += 1;
      window.requestAnimationFrame(frame);
    };
    window.requestAnimationFrame(frame);
  });

  let navigationStatus = null;
  let navigationError = false;
  try {
    const response = await page.goto(target.href, {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    navigationStatus = response?.status() ?? null;
  } catch {
    navigationError = true;
  }
  await page.waitForTimeout(14000);
  const report = await Promise.race([
    page.evaluate(() => {
      const summary = document.getElementById("health-summary-text");
      const cards = [...document.querySelectorAll("#service-health-overview strong")];
      return {
        summaryLoading: /loading/i.test(summary?.textContent || ""),
        loadingCards: cards.filter((card) => /loading/i.test(card.textContent || "")).length,
        publicRows: document.querySelectorAll("#public-services-list .public-service-card").length,
        detailedRows: document.querySelectorAll("#health-checks .health-row").length,
        statusFilterPresent: Boolean(document.getElementById("service-status-filter")),
        longTasks: window.__uiFreezeSample?.longTasks ?? null,
        longTaskTotalMs: Math.round(window.__uiFreezeSample?.longTaskTotalMs ?? 0),
        frames: window.__uiFreezeSample?.frames ?? null,
      };
    }),
    new Promise((resolve) => {
      setTimeout(() => resolve({ browserMainThreadUnresponsive: true }), 3000);
    }),
  ]);
  console.log(JSON.stringify({
    path: "/api",
    navigationStatus,
    navigationError,
    pageErrors,
    http: http.slice(-35),
    requestFailures: failed.slice(-15),
    ...report,
  }, null, 2));
} finally {
  await browser.close();
}
