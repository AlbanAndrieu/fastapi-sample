import test from "node:test";
import assert from "node:assert/strict";
import {
  setDatasetValueIfChanged,
} from "../../nabla/api/assets/api-dom-render-signature.js";

function trackedElement(initial = {}) {
  let mutationCount = 0;
  const values = { ...initial };
  const dataset = new Proxy(values, {
    set(target, property, value) {
      mutationCount += 1;
      target[property] = value;
      return true;
    },
  });
  return {
    element: { dataset },
    get mutations() { return mutationCount; },
  };
}

test("identical TrueNAS semantic status never retriggers observed attribute", () => {
  const tracked = trackedElement();
  assert.equal(setDatasetValueIfChanged(tracked.element, "semanticStatus", "operational"), true);
  for (let frame = 0; frame < 1000; frame += 1) {
    assert.equal(setDatasetValueIfChanged(tracked.element, "semanticStatus", "operational"), false);
  }
  assert.equal(tracked.mutations, 1);
});

test("actual status transitions trigger exactly one attribute mutation each", () => {
  const tracked = trackedElement({ semanticStatus: "unknown" });
  assert.equal(setDatasetValueIfChanged(tracked.element, "semanticStatus", "unknown"), false);
  assert.equal(setDatasetValueIfChanged(tracked.element, "semanticStatus", "operational"), true);
  assert.equal(setDatasetValueIfChanged(tracked.element, "semanticStatus", "operational"), false);
  assert.equal(setDatasetValueIfChanged(tracked.element, "semanticStatus", "degraded"), true);
  assert.equal(setDatasetValueIfChanged(tracked.element, "semanticStatus", "degraded"), false);
  assert.equal(tracked.mutations, 2);
});

test("unchanged probe lists and group metadata cause no attribute churn", () => {
  const tracked = trackedElement();
  const input = {
    presentationGroup: "core-critical",
    environments: "production",
    environmentSource: "runtime",
    probeKinds: "dns tcp tls http api",
    semanticStatus: "unknown",
  };
  for (let cycle = 0; cycle < 500; cycle += 1) {
    for (const [name, value] of Object.entries(input)) {
      setDatasetValueIfChanged(tracked.element, name, value);
    }
  }
  assert.equal(tracked.mutations, Object.keys(input).length);
});
