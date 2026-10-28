import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const content = readFileSync(
  fileURLToPath(new URL("../../nabla/api/assets/api-health.js", import.meta.url)),
  "utf8",
);
const body = content.slice(content.indexOf("async function bootstrapHealthUi()"));
const publicBranch = body.slice(0, body.indexOf("  const operatorMode ="));

test("public /api defaults to the bounded catalogue, before permission probes", () => {
  assert.match(publicBranch, /const publicFirst = params\.get\("ui_safe"\) === "1" \|\| !fullDashboardRequested/);
  assert.ok(publicBranch.indexOf("installPublicServiceOverview") > 0);
  assert.ok(body.indexOf("ownerSessionAvailable()") > body.indexOf("if (publicFirst)"));
  assert.ok(body.indexOf("installGlobalServiceFilter()") > body.indexOf("if (publicFirst)"));
});

test("detailed diagnostics remain explicitly opt-in, not privileged", () => {
  assert.match(body, /params\.get\("ui_full"\) === "1"/);
  assert.match(body, /params\.get\("operator"\) === "1"/);
  assert.match(body, /fullLink\.textContent = "Open detailed diagnostics"/);
  assert.match(body, /await Promise\.all\(\[\s*ownerSessionAvailable\(\),\s*diagnosticsReadAvailable\(\),/);
  assert.ok(!publicBranch.includes("ownerAuthenticated: true"));
});

test("explicit emergency safe mode never exposes advanced diagnostics", () => {
  assert.match(publicBranch, /params\.get\("ui_safe"\) !== "1"/);
  assert.match(publicBranch, /ownerAuthenticated: false/);
  assert.match(publicBranch, /element\.hidden = true/);
  assert.match(publicBranch, /health-cache-reset, \.health-refresh/);
});

test("normal public landing has no observer-based decorations", () => {
  assert.ok(!publicBranch.includes("new MutationObserver"));
  assert.ok(!publicBranch.includes("installHealthUiFinalFollowup()"));
  assert.ok(!publicBranch.includes("installHealthBoardController()"));
  assert.ok(!publicBranch.includes("installGlobalServiceFilter()"));
});

const entry = readFileSync(
  fileURLToPath(new URL("../../nabla/api/assets/api-health-entry.js", import.meta.url)),
  "utf8",
);
const page = readFileSync(
  fileURLToPath(new URL("../../nabla/api/ui.py", import.meta.url)),
  "utf8",
);

test("HTML selects a lightweight module with no eager rich UI imports", () => {
  assert.ok(page.includes('src="/api/assets/api-health-entry.js?v={app_version}"'));
  assert.ok(entry.includes('from "./api-public-services.js"'));
  assert.ok(entry.includes('import("./api-health.js")'));
  const topLevelImports = entry.split("\n").filter((line) =>
    line.startsWith("import ") && line.includes(" from ")
  );
  assert.deepEqual(topLevelImports, [
    'import { installPublicServiceOverview } from "./api-public-services.js";',
  ]);
  assert.ok(!entry.includes('from "./api-health-controller.js"'));
  assert.ok(!entry.includes('from "./api-health-ui-final-followup.js"'));
});

test("emergency safe always wins over requested full and operator modes", () => {
  assert.ok(entry.includes('const safeMode = params.get("ui_safe") === "1"'));
  assert.ok(entry.includes('params.get("ui_full") === "1" || params.get("operator") === "1"'));
  assert.ok(entry.includes("if (safeMode || !richMode)"));
  assert.ok(entry.includes("allowAdvancedLink: !safeMode"));
  assert.ok(entry.includes('target.searchParams.delete("ui_safe")'));
});

test("public mode never imports owner session, probes or DOM observers", () => {
  const publicOnly = entry.slice(0, entry.indexOf('  void import("./api-health.js")'));
  assert.ok(!publicOnly.includes("ownerSessionAvailable("));
  assert.ok(!publicOnly.includes("diagnosticsReadAvailable("));
  assert.ok(!publicOnly.includes("MutationObserver"));
  assert.ok(publicOnly.includes("installPublicServiceOverview({ ownerAuthenticated: false })"));
  assert.ok(entry.includes("void import(\"./api-health.js\").catch"));
});
