import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { homepageCadence } from "../../nabla/api/assets/home-cost-policy.js";

test("FastAPI Cloud anonymous pages stop recurring requests", () => {
  const plan = homepageCadence("fastapi_cloud", false);
  assert.equal(plan.pollEnabled, false);
  assert.equal(plan.pollIntervalMs, 180000);
  assert.deepEqual(plan.warmupDelaysMs, [15000]);
});

test("FastAPI Cloud OWNER diagnostics retain slow bounded refresh", () => {
  const plan = homepageCadence("fastapi_cloud", true);
  assert.equal(plan.pollEnabled, true);
  assert.equal(plan.pollIntervalMs, 180000);
});

test("TrueNAS continues historical 30s and 2/4/8/15/30 warmups", () => {
  const plan = homepageCadence("homelab", false);
  assert.equal(plan.pollEnabled, true);
  assert.equal(plan.pollIntervalMs, 30000);
  assert.deepEqual(plan.warmupDelaysMs, [2000, 4000, 8000, 15000, 30000]);
});

test("server runtime marker determines profile, not arbitrary browser state", () => {
  const template = readFileSync(
    new URL("../../templates/index.html", import.meta.url),
    "utf8",
  );
  const routes = readFileSync(
    new URL("../../nabla/routes.py", import.meta.url),
    "utf8",
  );
  const controller = readFileSync(
    new URL("../../nabla/api/assets/home-operations.js", import.meta.url),
    "utf8",
  );
  assert.match(template, /data-runtime-mode="{{ runtime_mode }}"/);
  assert.match(routes, /runtime_mode\(request\.url\.hostname\)/);
  assert.match(
    controller,
    /homepageCadence\(HOME_RUNTIME, ownerSessionActive\)/,
  );
  assert.match(
    controller,
    /if \(homepageCadence\(HOME_RUNTIME, ownerSessionActive\)\.pollEnabled\)/,
  );
});
