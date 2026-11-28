import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const controller = readFileSync(new URL("../../nabla/api/assets/api-health-controller.js", import.meta.url), "utf8");
const guide = readFileSync(new URL("../../nabla/api/assets/api-platform-flow-ui.js", import.meta.url), "utf8");

test("visible TrueNAS Core drill-down is hydrated without opening unrelated drawers", () => {
  assert.match(controller, /const trueNasPanel = document\.getElementById\("truenas-platform"\)/);
  assert.match(controller, /if \(trueNasPanel && !trueNasPanel\.hidden\) loadTrueNas\(\);/);
  assert.match(controller, /if \(includeTechnical\) loadRuntimeTopology\(\);/);
  assert.doesNotMatch(controller, /if \(includeTechnical\)\s*\{\s*loadRuntimeTopology\(\);\s*loadTrueNas\(\);/);
});

test("explanation remains visible without OWNER probe evidence and never invents TLD health", () => {
  assert.match(guide, /export function installPlatformFlowUi\(\) \{\s*\/\/[^\n]*[\s\S]*?ensureProtocolGuide\(\);/);
  assert.match(guide, /Domain \/ TLD registration \(not probed\)/);
  assert.match(guide, /DNS A\/AAAA resolution/);
  assert.match(guide, /TLS certificate \/ handshake/);
  assert.match(guide, /WebSocket \/ TrueNAS API/);
  assert.match(guide, /DNS TTL are not measured here/);
});
