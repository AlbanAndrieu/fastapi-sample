import test from "node:test";
import assert from "node:assert/strict";
import { reorderProbeNodesIfNeeded } from "../../nabla/api/assets/api-probe-stable-order.js";

function probe(name) {
  return { dataset: { probeKind: name } };
}
function fixture(names) {
  const children = names.map(probe);
  let mutationCount = 0;
  const strip = {
    children,
    appendChild(node) {
      const currentIndex = children.indexOf(node);
      if (currentIndex !== -1) children.splice(currentIndex, 1);
      children.push(node);
      mutationCount += 1;
    },
  };
  const order = new Map(["dns", "http", "tls", "metrics"].map((name, i) => [name, i]));
  return {
    strip, order, get mutations() { return mutationCount; },
    names: () => children.map((node) => node.dataset.probeKind),
  };
}

test("already sorted probes never emit a childList mutation", () => {
  const { strip, order, names, mutations } = fixture(["dns", "http", "tls"]);
  assert.equal(reorderProbeNodesIfNeeded(strip, [...strip.children], order), false);
  assert.deepEqual(names(), ["dns", "http", "tls"]);
  assert.equal(strip.children.length, 3);
  assert.equal(mutations, 0);
});

test("a single out-of-order refresh converges and stays stable", () => {
  const item = fixture(["metrics", "dns", "tls", "http"]);
  assert.equal(reorderProbeNodesIfNeeded(item.strip, [...item.strip.children], item.order), true);
  assert.deepEqual(item.names(), ["dns", "http", "tls", "metrics"]);
  const afterFirstPass = item.mutations;
  assert.ok(afterFirstPass > 0);
  for (let i = 0; i < 100; i += 1) {
    assert.equal(reorderProbeNodesIfNeeded(item.strip, [...item.strip.children], item.order), false);
  }
  assert.equal(item.mutations, afterFirstPass);
});

test("new probe labels get inserted only once then stabilize", () => {
  const item = fixture(["dns", "metrics"]);
  item.strip.children.push(probe("http"));
  assert.equal(reorderProbeNodesIfNeeded(item.strip, [...item.strip.children], item.order), true);
  assert.deepEqual(item.names(), ["dns", "http", "metrics"]);
  const stableCount = item.mutations;
  assert.equal(reorderProbeNodesIfNeeded(item.strip, [...item.strip.children], item.order), false);
  assert.equal(item.mutations, stableCount);
});

test("unknown probe names retain stable order without extra writes", () => {
  const item = fixture(["dns", "vendor-a", "vendor-b"]);
  assert.equal(reorderProbeNodesIfNeeded(item.strip, [...item.strip.children], item.order), false);
  assert.equal(item.mutations, 0);
});
