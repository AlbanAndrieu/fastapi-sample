// Run the project's no-secret Python Playwright diagnostic with live phase
// markers. Never leave the user waiting for an unresponsive Chromium page.
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const repo = dirname(dirname(fileURLToPath(import.meta.url)));
const diagnostic = join(repo, "scripts", "diagnose-api-ui-freeze.py");
const target = process.argv[2] || "cloud";
const safeMode = process.argv.includes("--safe");
const preflightMode = process.argv.includes("--preflight");
const nativeMode = preflightMode || process.argv.includes("--native");
const fullMode = process.argv.includes("--full");
const operatorMode = process.argv.includes("--operator");
if (safeMode && (fullMode || operatorMode)) {
  console.error(
    JSON.stringify({
      state: "invalid_browser_mode",
      allowed: ["--safe", "--operator", "--full", "--operator --full"],
    }),
  );
  process.exit(2);
}
const allowed = new Set(["cloud", "staging", "truenas"]);
if (!allowed.has(target)) {
  console.error(
    JSON.stringify({ state: "invalid_target", allowed: [...allowed] }),
  );
  process.exit(2);
}
// Preflight is a native, offline Python check; do not invoke uv because
// resolution/download may fail before the diagnostic gets a chance to report.
const executable = nativeMode ? process.env.API_UI_PYTHON || "python3" : "mise";
const args = nativeMode
  ? [diagnostic]
  : [
      "exec",
      "--",
      "uv",
      "run",
      "--no-project",
      "--with",
      "playwright",
      "python",
      diagnostic,
    ];
let child;
try {
  child = spawn(executable, args, {
    cwd: repo,
    env: {
      ...process.env,
      API_UI_TARGET: target,
      API_UI_SAFE: safeMode ? "1" : "0",
      API_UI_PREFLIGHT: preflightMode ? "1" : "0",
      API_UI_FULL: fullMode ? "1" : "0",
      API_UI_OPERATOR: operatorMode ? "1" : "0",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
} catch {
  console.error(
    JSON.stringify({
      state: "local_runner_unavailable",
      next_check: nativeMode
        ? "verify_native_python3_on_path"
        : "verify_mise_and_uv_on_path",
    }),
  );
  process.exit(2);
}
let phase = "spawn";
let buffer = "";
let finished = false;
let timedOut = false;
const timer = setTimeout(() => {
  timedOut = true;
  child.kill("SIGKILL");
}, 35_000);
child.stdout.setEncoding("utf8");
child.stdout.on("data", (part) => {
  const chunk = String(part);
  process.stdout.write(chunk);
  buffer = (buffer + chunk).slice(-4096);
  for (const line of chunk.split("\n")) {
    try {
      const data = JSON.parse(line);
      if (typeof data.phase === "string") phase = data.phase;
    } catch {
      // The final JSON report can be pretty-printed by an older version.
    }
  }
});
// Never echo raw browser/uv stderr: it may include private paths, URLs
// or tokens. Classify it into a fixed vocabulary for actionable failure.
let privateStderr = "";
child.stderr.setEncoding("utf8");
child.stderr.on("data", (part) => {
  privateStderr = (privateStderr + String(part)).slice(-8192);
});
function classifyRunnerFailure(raw) {
  const value = String(raw).toLowerCase();
  if (
    value.includes("mise: command not found") ||
    value.includes("mise: no such file")
  )
    return "mise_missing";
  if (
    value.includes("uv: command not found") ||
    value.includes("uv: no such file") ||
    value.includes("no such file or directory: uv")
  )
    return "uv_missing";
  if (value.includes("no module named playwright"))
    return "playwright_python_missing";
  if (value.includes("no module named pytest")) return "test_runner_missing";
  if (
    value.includes("network is unreachable") ||
    value.includes("failed to download") ||
    value.includes("failed to fetch") ||
    value.includes("offline mode")
  )
    return "uv_dependency_resolution_failed";
  if (value.includes("python") && value.includes("not found"))
    return "python_missing";
  return "runner_failure_unknown";
}
child.on("error", () => {
  if (finished) return;
  finished = true;
  clearTimeout(timer);
  console.error(
    JSON.stringify({
      state: "local_runner_unavailable",
      next_check: nativeMode
        ? "verify_native_python3_on_path"
        : "verify_mise_and_uv_on_path",
    }),
  );
  process.exitCode = 2;
});
child.on("close", (code) => {
  if (finished) return;
  finished = true;
  clearTimeout(timer);
  if (timedOut) {
    console.error(
      JSON.stringify({
        state: "browser_diagnostic_timeout",
        target,
        phase,
        next_check: "inspect_browser_main_thread_or_playwright_process",
      }),
    );
    process.exitCode = 2;
  } else if (code !== 0) {
    // Python prints a sanitized state if it initialized successfully.
    if (!buffer.includes('"state"')) {
      console.error(
        JSON.stringify({
          state: "browser_runner_failed",
          target,
          phase,
          runnerFailureClass: classifyRunnerFailure(privateStderr),
          next_check: nativeMode
            ? "verify_native_python3_on_path"
            : "verify_mise_uv_and_python_playwright",
        }),
      );
    }
    process.exitCode = code || 2;
  }
});
