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
