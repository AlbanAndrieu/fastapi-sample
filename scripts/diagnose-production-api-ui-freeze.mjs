// Run the project's no-secret Python Playwright diagnostic with live phase
// markers. Never leave the user waiting for an unresponsive Chromium page.
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const repo = dirname(dirname(fileURLToPath(import.meta.url)));
const diagnostic = join(repo, "scripts", "diagnose-production-api-ui-freeze.py");
const target = process.argv[2] || "cloud";
const allowed = new Set(["cloud", "staging", "truenas"]);
if (!allowed.has(target)) {
  console.error(JSON.stringify({ state: "invalid_target", allowed: [...allowed] }));
  process.exit(2);
}
const args = [
  "exec", "--", "uv", "run", "--no-project", "--with", "playwright",
  "python", diagnostic,
];
let child;
try {
  child = spawn("mise", args, {
    cwd: repo,
    env: { ...process.env, API_UI_TARGET: target },
    stdio: ["ignore", "pipe", "pipe"],
  });
} catch {
  console.error(JSON.stringify({ state: "local_runner_unavailable", next_check: "verify_mise_and_uv_on_path" }));
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
// Do not echo raw browser/uv stderr: it can contain page URLs or user data.
child.stderr.on("data", () => {});
child.on("error", () => {
  if (finished) return;
  finished = true;
  clearTimeout(timer);
  console.error(JSON.stringify({ state: "local_runner_unavailable", next_check: "verify_mise_and_uv_on_path" }));
  process.exitCode = 2;
});
child.on("close", (code) => {
  if (finished) return;
  finished = true;
  clearTimeout(timer);
  if (timedOut) {
    console.error(JSON.stringify({
      state: "browser_diagnostic_timeout", target, phase,
      next_check: "inspect_browser_main_thread_or_playwright_process",
    }));
    process.exitCode = 2;
  } else if (code !== 0) {
    // Python prints a sanitized state if it initialized successfully.
    if (!buffer.includes('"state"')) {
      console.error(JSON.stringify({
        state: "browser_diagnostic_failed", target, phase,
        next_check: "check_python_playwright_or_chromium",
      }));
    }
    process.exitCode = code || 2;
  }
});
