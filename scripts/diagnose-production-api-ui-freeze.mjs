// Preserve the existing Node entrypoint without requiring a second
// Playwright installation in node_modules. This project already maintains
// Python's pytest-playwright; uv installs Python Playwright in its own cache.
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const repo = dirname(dirname(fileURLToPath(import.meta.url)));
const diagnostic = join(repo, "scripts", "diagnose-production-api-ui-freeze.py");
const cmd = "mise";
const args = ["exec", "--", "uv", "run", "--no-project", "--with", "playwright", "python", diagnostic];
const result = spawnSync(cmd, args, {
  cwd: repo,
  env: process.env,
  stdio: "inherit",
  timeout: 50_000,
});
if (result.error) {
  const nextCheck =
    result.error.code === "ENOENT" ? "verify_mise_and_uv_on_path" :
    result.error.code === "ETIMEDOUT" ? "browser_diagnostic_timeout" :
    "inspect_local_python_playwright_runtime";
  console.error(JSON.stringify({ state: "local_runner_unavailable", next_check: nextCheck }));
  process.exitCode = 2;
} else {
  process.exitCode = result.status ?? 2;
}
