import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

test("public Cloud API dashboard does not auto-poll diagnostics", () => {
  const controller = readFileSync(
    new URL("../../nabla/api/assets/api-health-controller.js", import.meta.url),
    "utf8",
  );
  assert.match(controller, /CLOUD_COST_MODE/);
  assert.match(controller, /CLOUD_HEALTH_BOARD_IDLE_POLL_MS = 180000/);
  assert.match(controller, /CLOUD_HEALTH_BOARD_REFRESHING_POLL_MS = 15000/);
  assert.match(controller, /CLOUD_HEALTH_BOARD_ERROR_BACKOFF_MS = 180000/);
  assert.match(controller, /if \(CLOUD_COST_MODE\) \{/);
  assert.match(
    controller,
    /if \(!\(await ownerSessionAvailable\(\)\)\) return/,
  );
  assert.match(controller, /void installAutomaticRefresh\(\)/);
});

test("the two display surfaces identify costly Cloud vs TrueNAS behavior", () => {
  const policy = readFileSync(
    new URL("../../nabla/api/assets/home-cost-policy.js", import.meta.url),
    "utf8",
  );
  const home = readFileSync(
    new URL("../../nabla/api/assets/home-operations.js", import.meta.url),
    "utf8",
  );
  assert.match(policy, /pollEnabled: !cloud \|\| owner === true/);
  assert.match(home, /Inventaire public · sondes à exécuter sur demande/);
  assert.match(home, /Mode Cloud économique/);
  assert.match(home, /data-runtime-mode|HOME_RUNTIME/);
});
