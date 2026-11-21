import assert from "node:assert/strict";
import test from "node:test";

import { rowStatus } from "../../nabla/api/assets/api-service-groups.js";

// A row whose LED is blue (expected by design) or yellow, as rendered.
function ledRow(color) {
  return {
    dataset: {},
    querySelector: (selector) =>
      selector === `.health-led--${color}` ? {} : null,
  };
}

test("a LAN-skipped exposure check is Unknown, never Degraded", () => {
  const check = { skipped: true, expected_reachable: false, external: false };
  assert.equal(rowStatus(ledRow("blue"), check), "Unknown");
});

test("an unconfigured optional integration is Unknown, never Degraded", () => {
  assert.equal(rowStatus(ledRow("yellow"), { skipped: true }), "Unknown");
});

test("a probed warning keeps its Degraded status", () => {
  assert.equal(rowStatus(ledRow("yellow"), { reachable: true }), "Degraded");
});
