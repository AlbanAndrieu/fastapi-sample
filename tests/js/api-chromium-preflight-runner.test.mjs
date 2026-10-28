import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, chmodSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const runner = fileURLToPath(
  new URL("../../scripts/diagnose-production-api-ui-freeze.mjs", import.meta.url),
);

test("offline preflight launches native runner without mise or uv", () => {
  const temp = mkdtempSync(join(tmpdir(), "fastapi-chromium-probe-"));
  try {
    const python = join(temp, "synthetic-python");
    writeFileSync(python, [
      "#!/bin/sh",
      'printf "%s\\n" \'PRIVATE_SECRET_SHOULD_NOT_PRINT\' >&2',
      'printf "%s\\n" \'{"state":"playwright_python_missing","network_requests_sent":0}\'',
      "exit 2",
      "",
    ].join("\n"));
    chmodSync(python, 0o700);
    const result = spawnSync(process.execPath, [runner, "truenas", "--preflight"], {
      env: { ...process.env, API_UI_PYTHON: python },
      encoding: "utf8",
      timeout: 5000,
    });
    assert.equal(result.status, 2, result.error?.message);
    assert.match(result.stdout, /"state":"playwright_python_missing"/);
    assert.doesNotMatch(result.stderr, /PRIVATE_SECRET_SHOULD_NOT_PRINT/);
    assert.doesNotMatch(result.stderr, /browser_runner_failed/);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
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
