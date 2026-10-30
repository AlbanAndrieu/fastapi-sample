import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const runner = fileURLToPath(
  new URL("../../scripts/diagnose-production-api-ui-freeze.mjs", import.meta.url),
);

test("offline preflight launches native Python without mise, uv or network", (t) => {
  // On TrueNAS /tmp can be mounted noexec. An executable shell fixture under
  // tmpdir() can therefore fail before emitting JSON, even with chmod(0700).
  // Use the real installed interpreter for a truthful offline preflight.
  const python = process.env.API_UI_PYTHON || "python3";
  const available = spawnSync(python, ["--version"], {
    encoding: "utf8",
    timeout: 5000,
  });
  if (available.error || available.status !== 0) {
    t.skip("No usable native Python available; separate runner error test covers that case");
    return;
  }
  const result = spawnSync(process.execPath, [runner, "truenas", "--preflight"], {
    env: { ...process.env, API_UI_PYTHON: python },
    encoding: "utf8",
    timeout: 15000,
  });
  assert.equal(result.error, undefined, "Offline preflight process did not complete");
  assert.ok([0, 2].includes(result.status), "Unexpected preflight exit code");
  // A live Python preflight reports local dependency state, NEVER a request
  // or upstream outage. It does not launch a browser or visit a URL.
  let report;
  try {
    report = JSON.parse(result.stdout.trim());
  } catch {
    assert.fail("Native preflight emitted no valid JSON state (inspect sanitized runner status)");
  }
  const states = new Set([
    "playwright_python_missing",
    "playwright_driver_unavailable",
    "chromium_binary_missing",
    "browser_binary_ready",
  ]);
  assert.ok(states.has(report.state), "Unexpected native preflight state");
  assert.equal(result.status, report.state === "browser_binary_ready" ? 0 : 2);
  if ("network_requests_sent" in report) assert.equal(report.network_requests_sent, 0);
  assert.doesNotMatch(result.stderr, /PRIVATE_SECRET_SHOULD_NOT_PRINT/);
  assert.doesNotMatch(result.stderr, /browser_runner_failed/);
});

test("missing native Python is not mislabeled as a remote API outage", () => {
  const result = spawnSync(process.execPath, [runner, "truenas", "--preflight"], {
    env: { ...process.env, API_UI_PYTHON: "/nonexistent/fastapi-probe-python" },
    encoding: "utf8",
    timeout: 5000,
  });
  assert.equal(result.status, 2);
  assert.match(result.stderr, /"state":"local_runner_unavailable"/);
  assert.doesNotMatch(result.stderr, /"state":"main_thread_unresponsive"/);
});

test("safe and full modes cannot run simultaneously", () => {
  const result = spawnSync(
    process.execPath, [runner, "truenas", "--safe", "--full"],
    { encoding: "utf8", timeout: 5000 },
  );
  assert.equal(result.status, 2);
  assert.match(result.stderr, /"state":"invalid_browser_mode"/);
});


test("safe mode and operator mode cannot run simultaneously", () => {
  const result = spawnSync(process.execPath, [runner, "truenas", "--safe", "--operator"],
    { encoding: "utf8", timeout: 5000 });
  assert.equal(result.status, 2);
  assert.match(result.stderr, /"state":"invalid_browser_mode"/);
});

test("operator mode is forwarded to native preflight runner without credential headers", () => {
  const script = readFileSync(runner, "utf8");
  assert.match(script, /const operatorMode = process\.argv\.includes\("--operator"\)/);
  assert.match(script, /API_UI_OPERATOR: operatorMode \? "1" : "0"/);
  assert.doesNotMatch(script, /X-Diagnostics-Key/);
});
